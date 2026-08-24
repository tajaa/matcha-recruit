import Foundation

enum APIError: Error, LocalizedError {
    case httpError(Int, String)
    /// A failure whose `detail` was an OBJECT rather than a string — the shape
    /// tellus uses for anything a client needs to branch on rather than merely
    /// display (`{"code": "already_redeemed", "message": ..., ...extra}`, see
    /// PromoError in services/promo_service.py). The raw detail JSON rides
    /// along so each caller decodes only the extras it cares about instead of
    /// this enum growing a field per feature.
    case httpDetail(Int, String, Data)
    case serviceUnavailable(Int)
    case paymentRequired(String)
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
            return message
        case .serviceUnavailable(let code):
            if code == 502 || code == 503 || code == 504 {
                return "Server is updating. Try again in 30 seconds."
            }
            return "Server error (\(code)). Try again in a moment."
        case .httpDetail(_, let message, _):
            return message
        case .paymentRequired(let message):
            return message.isEmpty ? "This feature requires an active plan." : message
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
/// the side effect (e.g. a second redeem).
private func _isIdempotentMethod(_ method: String) -> Bool {
    let m = method.uppercased()
    return m == "GET" || m == "HEAD"
}

/// True only when the server DEFINITIVELY rejected the session during a
/// token-refresh attempt: a 401/403 from /auth/refresh, or no stored refresh
/// token (both surface as `APIError.unauthorized` / `httpError` 401/403).
/// Everything else — network blips, 5xx deploy windows, and decode errors
/// (a captive portal or proxy answering 200 with garbage) — is environmental:
/// logging out on those deletes a still-valid keychain refresh token and
/// forces a needless full re-login.
private func _isAuthRejection(_ error: Error) -> Bool {
    if case APIError.unauthorized = error { return true }
    if case APIError.httpError(let code, _) = error { return code == 401 || code == 403 }
    if case APIError.httpDetail(let code, _, _) = error { return code == 401 || code == 403 }
    return false
}

extension APIError {
    var statusCode: Int? {
        switch self {
        case .httpError(let code, _), .httpDetail(let code, _, _), .serviceUnavailable(let code):
            return code
        case .unauthorized: return 401
        default: return nil
        }
    }

    /// Decode the structured `detail` body, when there was one.
    func detail<T: Decodable>(as type: T.Type) -> T? {
        guard case .httpDetail(_, _, let data) = self else { return nil }
        return try? JSONDecoder().decode(type, from: data)
    }
}

class APIClient {
    static let shared = APIClient()

    /// Base API URL, including the `/api/tellus` path segment — service
    /// paths below start at "/auth/...", "/rewards/...", etc. Debug builds
    /// hit the local dev server (scripts/dev-remote.sh, :8001); release
    /// builds hit production. Override via `TELLUS_API_URL` for local
    /// testing against staging or a remote dev box.
    let baseURL: String = {
        if let override = ProcessInfo.processInfo.environment["TELLUS_API_URL"],
           !override.isEmpty {
            #if !DEBUG
            precondition(override.hasPrefix("https://"), "TELLUS_API_URL must use https:// in release builds (got: \(override))")
            #endif
            return override
        }
        #if DEBUG
        return "http://127.0.0.1:8001/api/tellus"
        #else
        return "https://hey-matcha.com/api/tellus"
        #endif
    }()

    /// `baseURL` with any trailing slashes and a trailing "/api/tellus" path
    /// segment stripped — suffix-anchored, because a global string replace
    /// corrupts api-subdomain hosts (e.g. "https://api.example.com/api/tellus"
    /// would otherwise be mangled). Used to derive `webOrigin` for handoffs
    /// to the web app (billing, stores, DMs — features not built natively).
    private var apiOrigin: String {
        var origin = baseURL
        while origin.hasSuffix("/") { origin = String(origin.dropLast()) }
        if origin.hasSuffix("/api/tellus") { origin = String(origin.dropLast("/api/tellus".count)) }
        return origin
    }

    /// Web-app origin for browser handoffs (billing, stores/QR, listings,
    /// prompts, DMs — v1 web-only features). A localhost base is the FastAPI
    /// backend, which serves no /tellus SPA route, so dev builds fall back
    /// to the prod web app.
    var webOrigin: String {
        let origin = apiOrigin
        if !origin.contains("127.0.0.1") && !origin.contains("localhost") {
            return origin
        }
        return "https://hey-matcha.com"
    }

    /// Bearer token. Read on every request from background executors and
    /// written from @MainActor (login / logout / refresh). Guard the
    /// non-atomic `Optional<String>` behind a lock — an unsynchronized
    /// read/write is a data race (a logout clearing it could tear a
    /// concurrent request's read).
    private let _tokenLock = NSLock()
    private var _accessToken: String?
    var accessToken: String? {
        get { _tokenLock.lock(); defer { _tokenLock.unlock() }; return _accessToken }
        set { _tokenLock.lock(); defer { _tokenLock.unlock() }; _accessToken = newValue }
    }

    /// Set by AppState to handle logout on a definitive 401/403.
    var onUnauthorized: (() -> Void)?
    /// Set by AppState to route a brand account to the billing wall on any
    /// runtime 402 (not just the plan_status check at login/restore).
    var onPaymentRequired: (() -> Void)?

    /// Shared failure policy for the 401 → refresh → retry path, stated ONCE
    /// so `request` and `requestData` cannot drift. Only a definitive
    /// rejection (`_isAuthRejection`) ends the session; every other failure
    /// rethrows untouched.
    private func failAfterRefreshFailure(_ error: Error) async throws -> Never {
        if _isAuthRejection(error) {
            await MainActor.run { onUnauthorized?() }
            throw APIError.unauthorized
        }
        throw error
    }

    private init() {
        accessToken = KeychainHelper.load(key: KeychainHelper.Keys.accessToken)

        if URLCache.shared.memoryCapacity < 20 * 1_000_000 {
            URLCache.shared = URLCache(
                memoryCapacity: 20 * 1_000_000,   // 20 MB
                diskCapacity: 100 * 1_000_000,    // 100 MB
                diskPath: nil
            )
        }
    }

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
        let snippet = String(data: data.prefix(64), encoding: .utf8)?
            .trimmingCharacters(in: .whitespacesAndNewlines).lowercased() ?? ""
        return snippet.hasPrefix("<!doctype") || snippet.hasPrefix("<html")
    }

    func request<T: Decodable>(
        method: String,
        path: String,
        body: (any Encodable)? = nil,
        headers: [String: String] = [:],
        retryOnUnauthorized: Bool = true,
        retryOnMaintenance: Bool = true
    ) async throws -> T {
        let data = try await requestData(
            method: method, path: path, body: body, headers: headers,
            retryOnUnauthorized: retryOnUnauthorized, retryOnMaintenance: retryOnMaintenance
        )
        // Decode off MainActor — large payloads used to hold up the main
        // thread when a VM `await`'d this function from MainActor context.
        do {
            return try await Task.detached(priority: .userInitiated) {
                let d = JSONDecoder()
                return try d.decode(T.self, from: data)
            }.value
        } catch {
            let isSensitive = path.contains("/auth") || path.lowercased().contains("token")
            let snippet = isSensitive ? "<redacted>" : (String(data: data.prefix(500), encoding: .utf8) ?? "<binary>")
            print("[APIClient] decode failed for \(T.self) at \(path): \(error.localizedDescription)\nresponse snippet: \(snippet)")
            throw APIError.decodingError(error)
        }
    }

    /// Fire-and-check for 204-No-Content endpoints (approve/decline/heart/
    /// notifications-read/etc.) — discards the (empty) body.
    func requestVoid(method: String, path: String, body: (any Encodable)? = nil, retryOnUnauthorized: Bool = true) async throws {
        _ = try await requestData(method: method, path: path, body: body, retryOnUnauthorized: retryOnUnauthorized)
    }

    func requestData(
        method: String,
        path: String,
        body: (any Encodable)? = nil,
        headers: [String: String] = [:],
        retryOnUnauthorized: Bool = true,
        retryOnMaintenance: Bool = true
    ) async throws -> Data {
        guard let url = URL(string: baseURL + path) else {
            throw APIError.invalidURL
        }
        var urlRequest = URLRequest(url: url)
        urlRequest.httpMethod = method

        // Honor Cache-Control / ETag headers on GETs. Mutations bypass the
        // cache — a cached 500/empty body must never mask a retry.
        urlRequest.cachePolicy = method.uppercased() == "GET" ? .useProtocolCachePolicy : .reloadIgnoringLocalCacheData

        if let token = accessToken {
            urlRequest.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        if let body = body {
            urlRequest.httpBody = try encoder.encode(body)
            urlRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        for (field, value) in headers {
            urlRequest.setValue(value, forHTTPHeaderField: field)
        }

        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await URLSession.shared.data(for: urlRequest)
        } catch {
            // DNS hiccup / brief disconnect / VPN flap — retry once after a
            // short delay. Only idempotent methods (see _isIdempotentMethod);
            // a mutating verb may have already been applied server-side.
            if let urlError = _isTransientNetworkError(error) {
                if retryOnMaintenance && _isIdempotentMethod(method) {
                    try? await Task.sleep(nanoseconds: 1_500_000_000)
                    return try await requestData(method: method, path: path, body: body, headers: headers, retryOnUnauthorized: retryOnUnauthorized, retryOnMaintenance: false)
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
                do {
                    _ = try await AuthService.shared.refresh()
                    return try await requestData(method: method, path: path, body: body, headers: headers, retryOnUnauthorized: false)
                } catch {
                    try await failAfterRefreshFailure(error)
                }
            } else {
                // retryOnUnauthorized == false ⇒ this is a credential endpoint
                // (login/signup/verify/resend) or the refresh call itself —
                // surface the server detail, don't nuke the session.
                // failAfterRefreshFailure() stays the ONLY onUnauthorized site.
                throw APIError.httpError(401, _extractErrorMessage(from: data) ?? "Unauthorized")
            }
        }

        if httpResponse.statusCode == 402 {
            await MainActor.run { onPaymentRequired?() }
            throw APIError.paymentRequired(_extractErrorMessage(from: data) ?? "")
        }

        guard (200...299).contains(httpResponse.statusCode) else {
            if _isTransientMaintenance(httpResponse, data: data) {
                if retryOnMaintenance && method.uppercased() == "GET" {
                    try? await Task.sleep(nanoseconds: 5_000_000_000)
                    return try await requestData(method: method, path: path, body: body, retryOnUnauthorized: retryOnUnauthorized, retryOnMaintenance: false)
                }
                throw APIError.serviceUnavailable(httpResponse.statusCode)
            }
            if let structured = _structuredDetail(from: data) {
                throw APIError.httpDetail(httpResponse.statusCode, structured.message, structured.detail)
            }
            let message = _extractErrorMessage(from: data) ?? "HTTP \(httpResponse.statusCode)"
            throw APIError.httpError(httpResponse.statusCode, message)
        }
        return data
    }

    /// Multipart form upload (currently: brand logo). Unlike the S3 presigned
    /// PUT path (MediaUploadService), this goes through APIClient with the
    /// bearer attached — the server itself receives and stores the file.
    func uploadMultipart<T: Decodable>(
        path: String, field: String = "file", data: Data, mimeType: String, filename: String
    ) async throws -> T {
        guard let url = URL(string: baseURL + path) else { throw APIError.invalidURL }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        let boundary = "tellus-" + UUID().uuidString
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        if let token = accessToken {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }

        var body = Data()
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"\(field)\"; filename=\"\(filename)\"\r\n".data(using: .utf8)!)
        body.append("Content-Type: \(mimeType)\r\n\r\n".data(using: .utf8)!)
        body.append(data)
        body.append("\r\n--\(boundary)--\r\n".data(using: .utf8)!)
        request.httpBody = body

        let (responseData, response) = try await URLSession.shared.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else { throw APIError.noData }

        if httpResponse.statusCode == 401 {
            _ = try await AuthService.shared.refresh()
            return try await uploadMultipart(path: path, field: field, data: data, mimeType: mimeType, filename: filename)
        }
        if httpResponse.statusCode == 402 {
            await MainActor.run { onPaymentRequired?() }
            throw APIError.paymentRequired(_extractErrorMessage(from: responseData) ?? "")
        }
        guard (200...299).contains(httpResponse.statusCode) else {
            if let structured = _structuredDetail(from: responseData) {
                throw APIError.httpDetail(httpResponse.statusCode, structured.message, structured.detail)
            }
            throw APIError.httpError(httpResponse.statusCode, _extractErrorMessage(from: responseData) ?? "HTTP \(httpResponse.statusCode)")
        }
        return try await Task.detached(priority: .userInitiated) {
            try JSONDecoder().decode(T.self, from: responseData)
        }.value
    }

    /// The structured `{"detail": {...}}` body, re-serialized, when the server
    /// sent an object rather than a plain string. Returns the caller-facing
    /// message alongside it — without this, an object detail fell through to
    /// the raw-body branch below and surfaced the whole JSON blob as the user's
    /// error message, with the `code` unreachable.
    func _structuredDetail(from data: Data) -> (message: String, detail: Data)? {
        guard let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let detail = json["detail"] as? [String: Any] else { return nil }
        let message = (detail["message"] as? String) ?? "Request failed"
        let encoded = (try? JSONSerialization.data(withJSONObject: detail)) ?? Data()
        return (message, encoded)
    }

    /// Extract a human-readable error from a typical FastAPI error response
    /// (`{"detail": "..."}`, `{"detail": {...}}`, or `{"detail": [...]}`) or
    /// fall back to the raw body.
    private func _extractErrorMessage(from data: Data) -> String? {
        if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
           let detail = json["detail"] as? String {
            return detail
        }
        if let structured = _structuredDetail(from: data) {
            return structured.message
        }
        // FastAPI request-validation shape: {"detail": [{"type":"...","loc":[...],"msg":"..."}]}
        if let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
           let detail = json["detail"] as? [[String: Any]] {
            if let first = detail.first {
                let msg = (first["msg"] as? String) ?? "Some fields need fixing."
                if let loc = first["loc"] as? [Any], let field = loc.last as? String, !field.isEmpty {
                    return "\(field): \(msg)"
                }
                return msg
            }
        }
        guard let raw = String(data: data, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines),
              !raw.isEmpty else { return nil }
        // An HTML error page (proxy/WAF block page, unmatched route) is never
        // a useful user-facing message.
        guard !raw.lowercased().hasPrefix("<") else { return nil }
        return String(raw.prefix(300))
    }
}

extension Error {
    /// True for task/URLSession cancellation — navigation away or a
    /// superseding load, never a failure the user should see.
    var isCancellation: Bool {
        self is CancellationError || (self as? URLError)?.code == .cancelled
    }
}
