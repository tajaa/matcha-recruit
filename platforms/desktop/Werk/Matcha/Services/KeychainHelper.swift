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

    // Use the data-protection keychain (kSecUseDataProtectionKeychain) instead
    // of the legacy file-based keychain. Legacy items carry a per-binary ACL,
    // so every Debug rebuild whose code signature varies re-triggers the
    // "Matcha wants to use your confidential information" prompt — and save()
    // re-creates the item on each token refresh, dropping any "Always Allow"
    // grant. Data-protection items are scoped to the app's access group
    // (TEAMID.bundleid), trusted by entitlement, so reads never prompt across
    // rebuilds or cert changes. Added 2026-05-21.
    /// Persist a value. Returns whether the write actually landed in the
    /// keychain — previously the `SecItemAdd` status was discarded, so a
    /// failed write (e.g. a keychain error, or an add attempted before first
    /// unlock under `AfterFirstUnlock`) looked identical to success. Uses
    /// add-then-update rather than the old delete-then-add: with
    /// delete-then-add, a failed add AFTER a successful delete destroyed the
    /// previously-good token — the exact silent-logout-on-next-launch bug
    /// this return value exists to surface. Add-or-update never removes an
    /// item without a replacement in hand. `@discardableResult` keeps
    /// best-effort callers unchanged.
    @discardableResult
    static func save(key: String, value: String) -> Bool {
        guard let data = value.data(using: .utf8) else { return false }
        let base: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrAccount as String: key,
            kSecUseDataProtectionKeychain as String: true
        ]
        var addQuery = base
        addQuery[kSecValueData as String] = data
        addQuery[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        var status = SecItemAdd(addQuery as CFDictionary, nil)
        if status == errSecDuplicateItem {
            let update: [String: Any] = [
                kSecValueData as String: data,
                kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
            ]
            status = SecItemUpdate(base as CFDictionary, update as CFDictionary)
        }
        if status != errSecSuccess {
            NSLog("[Keychain] save failed for \(key): OSStatus \(status)")
        }
        return status == errSecSuccess
    }

    static func load(key: String) -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrAccount as String: key,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne,
            kSecUseDataProtectionKeychain as String: true
        ]
        var result: AnyObject?
        let status = SecItemCopyMatching(query as CFDictionary, &result)
        if status == errSecSuccess,
           let data = result as? Data,
           let string = String(data: data, encoding: .utf8) {
            return string
        }
        // Not in the data-protection keychain — fall back to the legacy
        // keychain once and migrate it forward so existing users aren't logged
        // out by the storage switch. Self-cleaning: after migration the legacy
        // copy is removed and future loads hit the fast path above.
        return migrateLegacy(key: key)
    }

    static func delete(key: String) {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrAccount as String: key,
            kSecUseDataProtectionKeychain as String: true
        ]
        SecItemDelete(query as CFDictionary)
        deleteLegacy(key: key)
    }

    // MARK: - Legacy (file-based) keychain migration

    private static func migrateLegacy(key: String) -> String? {
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
        // Only drop the legacy copy once the data-protection write actually
        // succeeded — otherwise a failed migration destroys the only copy.
        if save(key: key, value: string) {
            deleteLegacy(key: key)
        }
        return string
    }

    private static func deleteLegacy(key: String) {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrAccount as String: key
        ]
        SecItemDelete(query as CFDictionary)
    }
}
