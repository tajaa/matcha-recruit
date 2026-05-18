import Foundation
import Security

/// Stores JWT access + refresh tokens in the macOS Keychain.
///
/// Previously had a `#if DEBUG` branch that fell back to UserDefaults to
/// work around a stale simulator-era issue. That branch wrote tokens to
/// `~/Library/Preferences/com.ahnimal.matcha.plist` as plaintext — any
/// debug build leaked them. Removed 2026-05-18; Keychain works fine in
/// debug builds.
///
/// Migration for older debug builds: `AppState.migrateKeychainTokens()`
/// reads any legacy UserDefaults entries on launch, copies them into
/// Keychain, then wipes the UserDefaults keys.
enum KeychainHelper {
    enum Keys {
        static let accessToken = "matcha.accessToken"
        static let refreshToken = "matcha.refreshToken"
    }

    static func save(key: String, value: String) {
        guard let data = value.data(using: .utf8) else { return }
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrAccount as String: key,
            kSecValueData as String: data,
            kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlock
        ]
        SecItemDelete(query as CFDictionary)
        SecItemAdd(query as CFDictionary, nil)
    }

    static func load(key: String) -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrAccount as String: key,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne
        ]
        var result: AnyObject?
        let status = SecItemCopyMatching(query as CFDictionary, &result)
        guard status == errSecSuccess,
              let data = result as? Data,
              let string = String(data: data, encoding: .utf8) else {
            return nil
        }
        return string
    }

    static func delete(key: String) {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrAccount as String: key
        ]
        SecItemDelete(query as CFDictionary)
    }
}
