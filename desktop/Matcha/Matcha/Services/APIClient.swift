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
    let baseURL = "http://127.0.0.1:8001/api"
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
            throw APIError.decodingError(error)
        }
    }

    func requestData(method: String, path: String, body: (any Encodable)? = nil) async throws -> Data {
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
        guard let httpResponse = response as? HTTPURLResponse,
              (200...299).contains(httpResponse.statusCode) else {
            throw APIError.noData
        }
        return data
    }
}
