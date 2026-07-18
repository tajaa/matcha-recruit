import Foundation

enum APIError: Error, LocalizedError {
    case httpError(Int, String)
    case serviceUnavailable(Int)
    case decodingError(Error)
    case unauthorized
    case invalidURL
    case noData
    case networkUnavailable(URLError)

    var errorDescription: String? {
        switch self {
        case .httpError(let code, let message):
            // Belt-and-suspenders: if a 5xx slipped through with an HTML body
            // and we didn't catch it via Content-Type, still collapse here.
            if (500...599).contains(code) {
                let trimmed = message.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
                if trimmed.hasPrefix("<!doctype") || trimmed.hasPrefix("<html") {
                    return APIError.serviceUnavailable(code).errorDescription
                }
            }
            return "HTTP \(code): \(message)"
        case .serviceUnavailable(let code):
            if code == 502 || code == 503 || code == 504 {
                return "Server is updating. Try again in 30 seconds."
            }
            return "Server error (\(code)). Try again in a moment."
        case .decodingError(let error):
            return "Decoding error: \(error.localizedDescription)"
        case .unauthorized:
            return "Unauthorized — please log in again"
        case .invalidURL:
            return "Invalid URL"
        case .noData:
            return "No data received"
        case .networkUnavailable(let urlError):
            switch urlError.code {
            case .notConnectedToInternet:
                return "No internet connection. Reconnect and try again."
            case .timedOut:
                return "Request timed out. Try again."
            case .cannotFindHost, .dnsLookupFailed:
                return "Couldn't reach the server. Check your network and try again."
            case .cannotConnectToHost, .networkConnectionLost:
                return "Lost connection to the server. Try again."
            default:
                return "Network error. Try again."
            }
        }
    }
}

/// URLError codes that indicate a probably-transient network failure worth
/// auto-retrying once before surfacing to the user.
private let _transientNetworkCodes: Set<URLError.Code> = [
    .cannotFindHost, .dnsLookupFailed, .networkConnectionLost,
    .timedOut, .cannotConnectToHost,
]

private func _isTransientNetworkError(_ error: Error) -> URLError? {
    guard let urlError = error as? URLError else { return nil }
    return _transientNetworkCodes.contains(urlError.code) ? urlError : nil
}

/// The single statement of which HTTP methods are safe to auto-retry after a
/// transient connection drop. A non-idempotent verb can have been received and
/// applied by the server before the connection died — replaying it duplicates
/// the side effect (e.g. a second Stripe checkout session).
private func _isIdempotentMethod(_ method: String) -> Bool {
    let m = method.uppercased()
    return m == "GET" || m == "HEAD"
}

/// True only when the server DEFINITIVELY rejected the session during a
/// token-refresh attempt: a 401/403 from /auth/refresh, or no stored refresh
/// token (both surface as `APIError.unauthorized` / `httpError` 401/403).
/// Everything else — network blips, 5xx deploy windows (including a plain
/// 500 with a JSON body that `_isTransientMaintenance` doesn't match), and
/// decode errors (a captive portal or proxy answering 200 with garbage) — is
/// environmental: logging out on those deletes a still-valid keychain
/// refresh token and forces a needless full re-login.
private func _isAuthRejection(_ error: Error) -> Bool {
    if case APIError.unauthorized = error { return true }
    if case APIError.httpError(let code, _) = error { return code == 401 || code == 403 }
    return false
}

class APIClient {
    static let shared = APIClient()

    /// Base API URL. Debug builds hit the local dev server; release builds
    /// (including notarized builds shipped to the team) hit production on EC2.
    /// Override via `MATCHA_API_URL` env var for local testing against staging
    /// or a remote dev box.
    let baseURL: String = {
        if let override = ProcessInfo.processInfo.environment["MATCHA_API_URL"],
           !override.isEmpty {
            #if !DEBUG
            precondition(override.hasPrefix("https://"), "MATCHA_API_URL must use https:// in release builds (got: \(override))")
            #endif
            return override
        }
        #if DEBUG
        return "http://127.0.0.1:8001/api"
        #else
        return "https://hey-matcha.com/api"
        #endif
    }()

    /// `baseURL` with any trailing slashes and a trailing "/api" path segment
    /// stripped — suffix-anchored, because a global string replace corrupts
    /// api-subdomain hosts (e.g. "https://api.example.com/api" →
    /// "https:/.example.com"). Shared by `webOrigin` and `wsBase`.
    private var apiOrigin: String {
        var origin = baseURL
        while origin.hasSuffix("/") { origin = String(origin.dropLast()) }
        if origin.hasSuffix("/api") { origin = String(origin.dropLast("/api".count)) }
        return origin
    }

    /// Web-app origin for browser redirects (Stripe success/cancel URLs).
    /// A localhost base is the FastAPI backend, which serves no /work SPA
    /// route, so dev builds fall back to the prod web app (the
    /// pre-derivation behavior).
    var webOrigin: String {
        let origin = apiOrigin
        if !origin.contains("127.0.0.1") && !origin.contains("localhost") {
            return origin
        }
        return "https://hey-matcha.com"
    }

    /// WebSocket base for the /ws/* endpoints: `apiOrigin` with http(s)
    /// swapped to ws(s). Unlike `webOrigin` there is NO prod fallback —
    /// sockets must reach the same host as the API, including localhost in
    /// DEBUG.
    var wsBase: String {
        let origin = apiOrigin
        if origin.hasPrefix("https://") { return "wss://" + origin.dropFirst("https://".count) }
        if origin.hasPrefix("http://") { return "ws://" + origin.dropFirst("http://".count) }
        return origin
    }
    /// Bearer token. Read on every request from background executors and
    /// written from @MainActor (login / logout / refresh). `APIClient` is a
    /// plain shared singleton, so guard the non-atomic `Optional<String>`
    /// behind a lock — the previous bare `var` was an unsynchronized read/write
    /// data race (a logout clearing it could tear a concurrent request's read).
    private let _tokenLock = NSLock()
    private var _accessToken: String?
    var accessToken: String? {
        get { _tokenLock.lock(); defer { _tokenLock.unlock() }; return _accessToken }
        set { _tokenLock.lock(); defer { _tokenLock.unlock() }; _accessToken = newValue }
    }

    // Will be set by AppState to handle logout on 401
    var onUnauthorized: (() -> Void)?

    /// Shared failure policy for the 401 → refresh → retry path, stated ONCE
    /// so `request` and `requestData` cannot drift (a fix applied to one and
    /// not the other would reintroduce destructive logout on exactly half the
    /// call surface). Only a definitive rejection (`_isAuthRejection`) ends
    /// the session; every other failure rethrows untouched. Note: a genuine
    /// refresh-POST 401 also fires onUnauthorized inside that nested request
    /// call — `didLogout` is idempotence-guarded, so the double signal is safe.
    private func failAfterRefreshFailure(_ error: Error) async throws -> Never {
        if _isAuthRejection(error) {
            await MainActor.run { onUnauthorized?() }
            throw APIError.unauthorized
        }
        throw error
    }

    private init() {
        // Restore cached token from keychain on launch
        accessToken = KeychainHelper.load(key: KeychainHelper.Keys.accessToken)

        // Configure shared URLCache so GETs honor the server's Cache-Control /
        // ETag headers automatically. Memory + disk cache shared across the
        // whole app — also covers AsyncImage avatar loads.
        if URLCache.shared.memoryCapacity < 20 * 1_000_000 {
            URLCache.shared = URLCache(
                memoryCapacity: 20 * 1_000_000,   // 20 MB
                diskCapacity: 100 * 1_000_000,    // 100 MB
                diskPath: nil
            )
        }
    }

    private let decoder: JSONDecoder = {
        let d = JSONDecoder()
        return d
    }()

    private let encoder: JSONEncoder = {
        let e = JSONEncoder()
        return e
    }()

    /// True if the response is a transient deploy/maintenance condition we
    /// should retry once before surfacing to the user.
    private func _isTransientMaintenance(_ httpResponse: HTTPURLResponse, data: Data) -> Bool {
        let code = httpResponse.statusCode
        guard code == 502 || code == 503 || code == 504 else { return false }
        let contentType = (httpResponse.value(forHTTPHeaderField: "Content-Type") ?? "").lowercased()
        if contentType.contains("text/html") { return true }
        // Body sniff fallback if Content-Type missing/wrong.
        let snippet = String(data: data.prefix(64), encoding: .utf8)?
            .trimmingCharacters(in: .whitespacesAndNewlines).lowercased() ?? ""
        return snippet.hasPrefix("<!doctype") || snippet.hasPrefix("<html")
    }

    func request<T: Decodable>(
        method: String,
        path: String,
        body: (any Encodable)? = nil,
        retryOnUnauthorized: Bool = true,
        retryOnMaintenance: Bool = true
    ) async throws -> T {
        guard let url = URL(string: baseURL + path) else {
            throw APIError.invalidURL
        }

        var urlRequest = URLRequest(url: url)
        urlRequest.httpMethod = method
        urlRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")

        // Honor Cache-Control / ETag headers on GETs. Mutations bypass the cache.
        if method.uppercased() == "GET" {
            urlRequest.cachePolicy = .useProtocolCachePolicy
        } else {
            urlRequest.cachePolicy = .reloadIgnoringLocalCacheData
        }

        if let token = accessToken {
            urlRequest.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }

        if let body = body {
            urlRequest.httpBody = try encoder.encode(body)
        }

        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await URLSession.shared.data(for: urlRequest)
        } catch {
            // DNS hiccup / brief disconnect / VPN flap — retry once after a
            // short delay, then surface a friendlier APIError so the UI shows
            // "Couldn't reach the server" instead of raw Foundation text.
            if let urlError = _isTransientNetworkError(error) {
                // Only auto-retry idempotent methods (see _isIdempotentMethod);
                // the maintenance path below is GET-gated for the same reason.
                if retryOnMaintenance && _isIdempotentMethod(method) {
                    try? await Task.sleep(nanoseconds: 1_500_000_000)
                    return try await request(method: method, path: path, body: body, retryOnUnauthorized: retryOnUnauthorized, retryOnMaintenance: false)
                }
                throw APIError.networkUnavailable(urlError)
            }
            throw error
        }

        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.noData
        }

        if httpResponse.statusCode == 401 {
            if retryOnUnauthorized {
                // Try to refresh
                do {
                    _ = try await AuthService.shared.refresh()
                    // Retry with new token
                    return try await request(method: method, path: path, body: body, retryOnUnauthorized: false)
                } catch {
                    try await failAfterRefreshFailure(error)
                }
            } else {
                await MainActor.run { onUnauthorized?() }
                throw APIError.unauthorized
            }
        }

        guard (200...299).contains(httpResponse.statusCode) else {
            if _isTransientMaintenance(httpResponse, data: data) {
                if retryOnMaintenance && method.uppercased() == "GET" {
                    try? await Task.sleep(nanoseconds: 5_000_000_000)
                    return try await request(method: method, path: path, body: body, retryOnUnauthorized: retryOnUnauthorized, retryOnMaintenance: false)
                }
                throw APIError.serviceUnavailable(httpResponse.statusCode)
            }
            let message = String(data: data, encoding: .utf8) ?? "Unknown error"
            throw APIError.httpError(httpResponse.statusCode, message)
        }

        // Decode off MainActor — large thread/project payloads (hundreds of
        // messages, KB of metadata) used to hold up the main thread when a
        // VM `await`'d this function from MainActor context.
        do {
            return try await Task.detached(priority: .userInitiated) {
                let d = JSONDecoder()
                return try d.decode(T.self, from: data)
            }.value
        } catch {
            // Surface a snippet of the actual payload so "decoding error" is
            // actionable instead of opaque. Without this we get the generic
            // "data couldn't be read" Foundation message and have no idea
            // which field/shape mismatched.
            let isSensitive = path.contains("/auth") || path.lowercased().contains("token")
            let snippet = isSensitive ? "<redacted>" : (String(data: data.prefix(500), encoding: .utf8) ?? "<binary>")
            print("[APIClient] decode failed for \(T.self) at \(path): \(error.localizedDescription)\nresponse snippet: \(snippet)")
            throw APIError.decodingError(error)
        }
    }

    func requestData(
        method: String,
        path: String,
        body: (any Encodable)? = nil,
        retryOnUnauthorized: Bool = true,
        retryOnMaintenance: Bool = true
    ) async throws -> Data {
        guard let url = URL(string: baseURL + path) else {
            throw APIError.invalidURL
        }
        var urlRequest = URLRequest(url: url)
        urlRequest.httpMethod = method
        // Binary endpoints (PDF, DOCX, signed-PDF download) should bypass
        // URLCache. Without this, an earlier 500 response can be cached
        // and subsequent retries return stale empty/error bodies.
        urlRequest.cachePolicy = .reloadIgnoringLocalCacheData
        if let token = accessToken {
            urlRequest.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        if let body = body {
            urlRequest.httpBody = try encoder.encode(body)
            urlRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await URLSession.shared.data(for: urlRequest)
        } catch {
            if let urlError = _isTransientNetworkError(error) {
                // Idempotent-only retry — see _isIdempotentMethod; never replay
                // a mutating verb that may have already been applied.
                if retryOnMaintenance && _isIdempotentMethod(method) {
                    try? await Task.sleep(nanoseconds: 1_500_000_000)
                    return try await requestData(method: method, path: path, body: body, retryOnUnauthorized: retryOnUnauthorized, retryOnMaintenance: false)
                }
                throw APIError.networkUnavailable(urlError)
            }
            throw error
        }
        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.noData
        }

        // Mirror request<T> 401 refresh logic — without this, channel
        // reactions and any other requestData-backed call silently fail
        // when the access token expires instead of refreshing + retrying.
        if httpResponse.statusCode == 401 {
            if retryOnUnauthorized {
                do {
                    _ = try await AuthService.shared.refresh()
                    return try await requestData(method: method, path: path, body: body, retryOnUnauthorized: false)
                } catch {
                    try await failAfterRefreshFailure(error)
                }
            } else {
                await MainActor.run { onUnauthorized?() }
                throw APIError.unauthorized
            }
        }

        // Don't collapse non-2xx into "noData" — throw the real status +
        // body so callers display actionable errors ("403 Not a member"
        // instead of "No data received").
        guard (200...299).contains(httpResponse.statusCode) else {
            if _isTransientMaintenance(httpResponse, data: data) {
                if retryOnMaintenance && method.uppercased() == "GET" {
                    try? await Task.sleep(nanoseconds: 5_000_000_000)
                    return try await requestData(method: method, path: path, body: body, retryOnUnauthorized: retryOnUnauthorized, retryOnMaintenance: false)
                }
                throw APIError.serviceUnavailable(httpResponse.statusCode)
            }
            let message = _extractErrorMessage(from: data) ?? "HTTP \(httpResponse.statusCode)"
            throw APIError.httpError(httpResponse.statusCode, message)
        }
        return data
    }

    /// Extract a human-readable error from a typical FastAPI error response
    /// (`{"detail": "..."}`) or fall back to the raw body.
    private func _extractErrorMessage(from data: Data) -> String? {
        if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
           let detail = json["detail"] as? String {
            return detail
        }
        let raw = String(data: data, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines)
        return raw?.isEmpty == false ? raw : nil
    }
}

extension Error {
    /// True for task/URLSession cancellation — navigation away or a
    /// superseding load, never a failure the user should see. One shared
    /// definition so catch sites can't drift between the two shapes
    /// (`is CancellationError` alone misses URLSession-level cancels).
    var isCancellation: Bool {
        self is CancellationError || (self as? URLError)?.code == .cancelled
    }
}
