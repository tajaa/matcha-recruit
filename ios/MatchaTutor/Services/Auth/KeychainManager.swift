import Foundation
import Security

enum KeychainError: Error {
    case duplicateItem
    case itemNotFound
    case unexpectedData
    case unhandledError(status: OSStatus)
}

final class KeychainManager {
    static let shared = KeychainManager()

    private let service = "com.matcha.tutor"

    private enum Keys {
        static let accessToken = "access_token"
        static let refreshToken = "refresh_token"
        static let tokenExpiry = "token_expiry"
    }

    private init() {}

    // MARK: - Access Token

    func saveAccessToken(_ token: String) throws {
        try save(key: Keys.accessToken, data: token.data(using: .utf8)!)
    }

    func getAccessToken() -> String? {
        guard let data = try? get(key: Keys.accessToken) else { return nil }
        return String(data: data, encoding: .utf8)
    }

    func deleteAccessToken() throws {
        try delete(key: Keys.accessToken)
    }

    // MARK: - Refresh Token

    func saveRefreshToken(_ token: String) throws {
        try save(key: Keys.refreshToken, data: token.data(using: .utf8)!)
    }

    func getRefreshToken() -> String? {
        guard let data = try? get(key: Keys.refreshToken) else { return nil }
        return String(data: data, encoding: .utf8)
    }

    func deleteRefreshToken() throws {
        try delete(key: Keys.refreshToken)
    }

    // MARK: - Token Expiry

    func saveTokenExpiry(_ date: Date) throws {
        let timestamp = date.timeIntervalSince1970
        let data = withUnsafeBytes(of: timestamp) { Data($0) }
        try save(key: Keys.tokenExpiry, data: data)
    }

    func getTokenExpiry() -> Date? {
        guard let data = try? get(key: Keys.tokenExpiry),
              data.count == MemoryLayout<TimeInterval>.size else { return nil }
        let timestamp = data.withUnsafeBytes { $0.load(as: TimeInterval.self) }
        return Date(timeIntervalSince1970: timestamp)
    }

    func deleteTokenExpiry() throws {
        try delete(key: Keys.tokenExpiry)
    }

    // MARK: - Clear All

    func clearAll() {
        try? deleteAccessToken()
        try? deleteRefreshToken()
        try? deleteTokenExpiry()
    }

    // MARK: - Private Helpers

    private func save(key: String, data: Data) throws {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key,
            kSecValueData as String: data,
            kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        ]

        let status = SecItemAdd(query as CFDictionary, nil)

        if status == errSecDuplicateItem {
            let updateQuery: [String: Any] = [
                kSecClass as String: kSecClassGenericPassword,
                kSecAttrService as String: service,
                kSecAttrAccount as String: key
            ]
            let updateAttributes: [String: Any] = [
                kSecValueData as String: data
            ]
            let updateStatus = SecItemUpdate(updateQuery as CFDictionary, updateAttributes as CFDictionary)
            guard updateStatus == errSecSuccess else {
                throw KeychainError.unhandledError(status: updateStatus)
            }
        } else if status != errSecSuccess {
            throw KeychainError.unhandledError(status: status)
        }
    }

    private func get(key: String) throws -> Data {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne
        ]

        var result: AnyObject?
        let status = SecItemCopyMatching(query as CFDictionary, &result)

        guard status == errSecSuccess else {
            if status == errSecItemNotFound {
                throw KeychainError.itemNotFound
            }
            throw KeychainError.unhandledError(status: status)
        }

        guard let data = result as? Data else {
            throw KeychainError.unexpectedData
        }

        return data
    }

    private func delete(key: String) throws {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key
        ]

        let status = SecItemDelete(query as CFDictionary)

        guard status == errSecSuccess || status == errSecItemNotFound else {
            throw KeychainError.unhandledError(status: status)
        }
    }
}
