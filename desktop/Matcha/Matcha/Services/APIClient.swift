import Foundation

enum APIError: Error, LocalizedError {
    case httpError(Int, String)
    case serviceUnavailable(Int)
    case decodingError(Error)
    case unauthorized
    case invalidURL
    case noData

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
        }
    }
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
            return override
        }
        #if DEBUG
        return "http://127.0.0.1:8001/api"
        #else
        return "https://hey-matcha.com/api"
        #endif
    }()
    var accessToken: String?

    // Will be set by AppState to handle logout on 401
    var onUnauthorized: (() -> Void)?

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

        let (data, response) = try await URLSession.shared.data(for: urlRequest)

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
                    await MainActor.run { onUnauthorized?() }
                    throw APIError.unauthorized
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
            let snippet = String(data: data.prefix(500), encoding: .utf8) ?? "<binary>"
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
        let (data, response) = try await URLSession.shared.data(for: urlRequest)
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
                    await MainActor.run { onUnauthorized?() }
                    throw APIError.unauthorized
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
