import Foundation
import Security

enum SessionKeychain {
    static let key = "cappe.storefront.v2.\(Config.current.slug)"
    static var query: [String: Any] { [kSecClass as String: kSecClassGenericPassword, kSecAttrAccount as String: key, kSecUseDataProtectionKeychain as String: true] }
    static func load() -> Tokens? {
        var q = query; q[kSecReturnData as String] = true; q[kSecMatchLimit as String] = kSecMatchLimitOne
        var result: CFTypeRef?
        guard SecItemCopyMatching(q as CFDictionary, &result) == errSecSuccess, let data = result as? Data else { return nil }
        return try? JSONDecoder().decode(Tokens.self, from: data)
    }
    static func save(_ tokens: Tokens) throws {
        let data = try JSONEncoder().encode(tokens)
        let fields: [String: Any] = [kSecValueData as String: data, kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly]
        var status = SecItemUpdate(query as CFDictionary, fields as CFDictionary)
        if status == errSecItemNotFound { status = SecItemAdd(query.merging(fields) { _, new in new } as CFDictionary, nil) }
        guard status == errSecSuccess else { throw APIError(status: 0, message: "Could not securely save your session. Please try again.") }
    }
    static func clear() { SecItemDelete(query as CFDictionary) }
}

enum StorefrontURL {
    /// Foundation leaves "+" literal in a percent-encoded query, while the
    /// server's form-style query parser decodes it as a space.
    static func queryString(_ items: [URLQueryItem]) -> String {
        var components = URLComponents()
        components.queryItems = items
        return components.percentEncodedQuery
            .map { "?" + $0.replacingOccurrences(of: "+", with: "%2B") }
            ?? ""
    }
}

@MainActor final class StorefrontAPI {
    static let shared = StorefrontAPI()
    let config = Config.current
    var tokens = SessionKeychain.load()
    private var refreshTask: Task<Tokens, Error>?
    static let decoder: JSONDecoder = { let d = JSONDecoder(); d.keyDecodingStrategy = .convertFromSnakeCase; return d }()

    func request<T: Decodable>(_ path: String, method: String = "GET", body: [String: Any]? = nil, authenticated: Bool = true) async throws -> T {
        let oldAccess = tokens?.accessToken
        do { return try await send(path, method: method, body: body, access: authenticated ? oldAccess : nil) }
        catch let error as APIError where error.status == 401 && authenticated && tokens != nil {
            if oldAccess == tokens?.accessToken { try await refresh() }
            return try await send(path, method: method, body: body, access: tokens?.accessToken)
        }
    }
    private func send<T: Decodable>(_ path: String, method: String, body: [String: Any]?, access: String?) async throws -> T {
        guard let url = URL(string: config.apiBase.absoluteString + path) else { throw APIError(status: 0, message: "Invalid store address") }
        var request = URLRequest(url: url); request.httpMethod = method; request.timeoutInterval = 30
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if let access { request.setValue("Bearer \(access)", forHTTPHeaderField: "Authorization") }
        if let body { request.httpBody = try JSONSerialization.data(withJSONObject: body) }
        // Only reads are automatically replayed. Retrying checkout after a
        // timeout could create a second purchase.
        for attempt in 0...1 {
            do {
                let (data, response) = try await URLSession.shared.data(for: request)
                let status = (response as? HTTPURLResponse)?.statusCode ?? 0
                if method == "GET", attempt == 0, [429, 502, 503, 504].contains(status) {
                    try await Task.sleep(for: .seconds(1)); continue
                }
                guard (200...299).contains(status) else {
                    let json = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
                    throw APIError(status: status, message: json?["detail"] as? String ?? "The store could not complete this request (\(status)).")
                }
                return try Self.decoder.decode(T.self, from: data.isEmpty ? Data("{}".utf8) : data)
            } catch let error as URLError where method == "GET" && attempt == 0 && [.timedOut, .networkConnectionLost].contains(error.code) {
                try await Task.sleep(for: .seconds(1))
            }
        }
        throw APIError(status: 0, message: "Connection interrupted. Please retry.")
    }
    func refresh() async throws {
        if let refreshTask { _ = try await refreshTask.value; return }
        guard let refresh = tokens?.refreshToken else { throw APIError(status: 401, message: "Please sign in") }
        let task = Task<Tokens, Error> {
            let pair: Tokens = try await self.send(self.config.shopperPath + "/auth/refresh", method: "POST", body: ["refresh_token": refresh], access: nil)
            try SessionKeychain.save(pair); self.tokens = pair
            return pair
        }
        refreshTask = task
        defer { refreshTask = nil }
        do { _ = try await task.value }
        catch let error as APIError where error.status == 401 { clear(); throw error }
    }
    func save(_ pair: Tokens) throws { try SessionKeychain.save(pair); tokens = pair }
    func clear() { tokens = nil; SessionKeychain.clear(); NotificationCenter.default.post(name: .storeSessionEnded, object: nil) }
}
extension Notification.Name {
    static let storeSessionEnded = Notification.Name("storeSessionEnded")
    static let storeOrderLink = Notification.Name("storeOrderLink")
    static let storeDeviceToken = Notification.Name("storeDeviceToken")
}
