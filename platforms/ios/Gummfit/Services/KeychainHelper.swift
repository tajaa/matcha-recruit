import Foundation
import Security

/// Stores JWT access + refresh tokens in the iOS Keychain, scoped to the
/// Gummfit (Cappe) app — separate keys from any other matcha app on the same
/// device (e.g. Tell-Us, which uses "tellus.*").
enum KeychainHelper {
    enum Keys {
        static let accessToken = "cappe.accessToken"
        static let refreshToken = "cappe.refreshToken"
    }

    // Use the data-protection keychain (kSecUseDataProtectionKeychain) rather
    // than the legacy file-based keychain — legacy items carry a per-binary
    // ACL, so every Debug rebuild whose code signature varies re-triggers a
    // system prompt, and save() re-creates the item on each refresh, dropping
    // any "Always Allow" grant. Data-protection items are scoped to the app's
    // access group and trusted by entitlement, so reads never prompt across
    // rebuilds or cert changes.
    /// Persist a value. Returns whether the write actually landed in the
    /// keychain — a failed write (e.g. attempted before first unlock under
    /// AfterFirstUnlock) must not look identical to success. Uses
    /// update-first-then-add rather than delete-then-add: with
    /// delete-then-add, a failed add AFTER a successful delete destroys the
    /// previously-good token — a silent-logout-on-next-launch bug. Add-or-
    /// update never removes an item without a replacement in hand.
    @discardableResult
    static func save(key: String, value: String) -> Bool {
        guard let data = value.data(using: .utf8) else { return false }
        let base: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrAccount as String: key,
            kSecUseDataProtectionKeychain as String: true
        ]
        let update: [String: Any] = [
            kSecValueData as String: data,
            kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        ]
        var status = SecItemUpdate(base as CFDictionary, update as CFDictionary)
        if status == errSecItemNotFound {
            var addQuery = base
            addQuery[kSecValueData as String] = data
            addQuery[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
            status = SecItemAdd(addQuery as CFDictionary, nil)
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
        return nil
    }

    static func delete(key: String) {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrAccount as String: key,
            kSecUseDataProtectionKeychain as String: true
        ]
        SecItemDelete(query as CFDictionary)
    }
}
