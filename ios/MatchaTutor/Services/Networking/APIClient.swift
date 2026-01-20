import Foundation

enum APIError: Error, LocalizedError {
    case invalidURL
    case invalidResponse
    case httpError(statusCode: Int, message: String?)
    case decodingError(Error)
    case networkError(Error)
    case unauthorized
    case tokenRefreshFailed

    var errorDescription: String? {
        switch self {
        case .invalidURL:
            return "Invalid URL"
        case .invalidResponse:
            return "Invalid response from server"
        case .httpError(let code, let message):
            return message ?? "HTTP error \(code)"
        case .decodingError(let error):
            return "Failed to decode response: \(error.localizedDescription)"
        case .networkError(let error):
            return "Network error: \(error.localizedDescription)"
        case .unauthorized:
            return "Session expired. Please log in again."
        case .tokenRefreshFailed:
            return "Failed to refresh authentication. Please log in again."
        }
    }
}

struct APIErrorResponse: Codable {
    let detail: String?
    let message: String?

    var errorMessage: String? {
        detail ?? message
    }
}

final class APIClient {
    static let shared = APIClient()

    #if DEBUG
    private let baseURL = "http://localhost:8001/api"
    #else
    private let baseURL = "https://api.matcha.example.com/api" // Replace with production URL
    #endif

    private let session: URLSession
    private let tokenManager = TokenManager.shared
    private let decoder: JSONDecoder
    private let encoder: JSONEncoder

    private init() {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 30
        config.timeoutIntervalForResource = 60
        session = URLSession(configuration: config)

        decoder = JSONDecoder()
        encoder = JSONEncoder()
    }

    // MARK: - Auth Endpoints

    func login(email: String, password: String) async throws -> TokenResponse {
        let request = LoginRequest(email: email, password: password)
        let response: TokenResponse = try await post(path: "/auth/login", body: request, authenticated: false)
        tokenManager.saveTokens(from: response)
        return response
    }

    func getCurrentUser() async throws -> CurrentUserResponse {
        return try await get(path: "/auth/me")
    }

    func logout() {
        tokenManager.clearTokens()
    }

    func refreshToken() async throws -> TokenResponse {
        guard let refreshToken = tokenManager.refreshToken else {
            throw APIError.unauthorized
        }

        struct RefreshRequest: Codable {
            let refreshToken: String

            enum CodingKeys: String, CodingKey {
                case refreshToken = "refresh_token"
            }
        }

        let request = RefreshRequest(refreshToken: refreshToken)
        let response: TokenResponse = try await post(path: "/auth/refresh", body: request, authenticated: false)
        tokenManager.saveTokens(from: response)
        return response
    }

    // MARK: - Tutor Endpoints

    func createTutorSession(mode: TutorMode, language: TutorLanguage?, durationMinutes: Int?, interviewRole: String?) async throws -> TutorSessionResponse {
        let request = TutorSessionCreateRequest(
            mode: mode,
            language: language,
            durationMinutes: durationMinutes,
            interviewRole: interviewRole
        )
        return try await post(path: "/tutor/sessions", body: request)
    }

    func getTutorSessions() async throws -> [TutorSessionSummary] {
        return try await get(path: "/tutor/sessions")
    }

    // MARK: - Generic Request Methods

    private func get<T: Decodable>(path: String, authenticated: Bool = true) async throws -> T {
        let request = try await makeRequest(path: path, method: "GET", authenticated: authenticated)
        return try await execute(request)
    }

    private func post<T: Decodable, B: Encodable>(path: String, body: B, authenticated: Bool = true) async throws -> T {
        var request = try await makeRequest(path: path, method: "POST", authenticated: authenticated)
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try encoder.encode(body)
        return try await execute(request)
    }

    private func makeRequest(path: String, method: String, authenticated: Bool) async throws -> URLRequest {
        guard let url = URL(string: baseURL + path) else {
            throw APIError.invalidURL
        }

        var request = URLRequest(url: url)
        request.httpMethod = method

        if authenticated {
            // Check if token needs refresh
            if tokenManager.shouldRefreshToken && tokenManager.refreshToken != nil {
                do {
                    _ = try await refreshToken()
                } catch {
                    throw APIError.tokenRefreshFailed
                }
            }

            guard let authHeader = tokenManager.authorizationHeader else {
                throw APIError.unauthorized
            }
            request.setValue(authHeader, forHTTPHeaderField: "Authorization")
        }

        return request
    }

    private func execute<T: Decodable>(_ request: URLRequest) async throws -> T {
        let (data, response): (Data, URLResponse)

        do {
            (data, response) = try await session.data(for: request)
        } catch {
            throw APIError.networkError(error)
        }

        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.invalidResponse
        }

        switch httpResponse.statusCode {
        case 200...299:
            do {
                return try decoder.decode(T.self, from: data)
            } catch {
                throw APIError.decodingError(error)
            }
        case 401:
            tokenManager.clearTokens()
            throw APIError.unauthorized
        default:
            let errorMessage = try? decoder.decode(APIErrorResponse.self, from: data)
            throw APIError.httpError(statusCode: httpResponse.statusCode, message: errorMessage?.errorMessage)
        }
    }
}
