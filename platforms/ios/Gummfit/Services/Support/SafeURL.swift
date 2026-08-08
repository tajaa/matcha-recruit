import Foundation
import UIKit

/// Gatekeeper for handing URLs to `UIApplication.shared.open(...)`.
///
/// Any URL that originates from network / user content (product photos,
/// site logos, web handoff links) must go through here. `UIApplication.open`
/// will launch any scheme the system can handle, so we only allow
/// `http`/`https`.
enum SafeURL {
    private static let allowedSchemes: Set<String> = ["http", "https"]

    private static func isSafe(_ url: URL) -> Bool {
        guard let scheme = url.scheme?.lowercased() else { return false }
        return allowedSchemes.contains(scheme)
    }

    /// Open an external URL string only if its scheme is http/https. Returns
    /// true if it opened. Silently ignores other schemes.
    @discardableResult
    static func open(_ raw: String?) -> Bool {
        guard let raw, let url = URL(string: raw), isSafe(url) else { return false }
        UIApplication.shared.open(url)
        return true
    }

    /// Open a pre-parsed external URL only if its scheme is http/https.
    @discardableResult
    static func open(_ url: URL?) -> Bool {
        guard let url, isSafe(url) else { return false }
        UIApplication.shared.open(url)
        return true
    }
}
