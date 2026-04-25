import Foundation

enum APIError: Error, LocalizedError {
    case httpError(Int, String)
    case decodingError(Error)
    case unauthorized
    case invalidURL
    case noData

    var errorDescription: String? {
        switch self {
        case .httpError(let code, let message):
            // Server returns an HTML "Updating in progress" page during deploys
            // (502/503/504). Don't dump raw HTML into an alert — collapse to a
            // friendly retry message. Same for any other 5xx body that looks
            // like HTML rather than JSON {detail: "..."}.
            if (500...599).contains(code) {
                let trimmed = message.trimmingCharacters(in: .whitespacesAndNewlines)
                if trimmed.lowercased().hasPrefix("<!doctype") || trimmed.hasPrefix("<html") {
                    if code == 502 || code == 503 || code == 504 {
                        return "Server is updating. Try again in 30 seconds."
                    }
                    return "Server error (\(code)). Try again in a moment."
                }
            }
            return "HTTP \(code): \(message)"
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
    }

    private let decoder: JSONDecoder = {
        let d = JSONDecoder()
        return d
    }()

    private let encoder: JSONEncoder = {
        let e = JSONEncoder()
        return e
    }()

    func request<T: Decodable>(
        method: String,
        path: String,
        body: (any Encodable)? = nil,
        retryOnUnauthorized: Bool = true
    ) async throws -> T {
        guard let url = URL(string: baseURL + path) else {
            throw APIError.invalidURL
        }

        var urlRequest = URLRequest(url: url)
        urlRequest.httpMethod = method
        urlRequest.setValue("application/json", forHTTPHeaderField: "Content-Type")

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
            let message = String(data: data, encoding: .utf8) ?? "Unknown error"
            throw APIError.httpError(httpResponse.statusCode, message)
        }

        do {
            return try decoder.decode(T.self, from: data)
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
        retryOnUnauthorized: Bool = true
    ) async throws -> Data {
        guard let url = URL(string: baseURL + path) else {
            throw APIError.invalidURL
        }
        var urlRequest = URLRequest(url: url)
        urlRequest.httpMethod = method
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
