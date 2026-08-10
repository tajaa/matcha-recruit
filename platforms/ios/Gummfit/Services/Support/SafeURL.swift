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

    /// Parse + scheme-check without opening — for SwiftUI `Link`, which
    /// opens the URL itself and never reaches `open(_:)`.
    static func validated(_ raw: String?) -> URL? {
        guard let raw, let url = URL(string: raw), isSafe(url) else { return nil }
        return url
    }

    /// Resolves a public asset URL from the API. Local storage returns paths
    /// such as `/uploads/resumes/photo.jpg`; a browser resolves those against
    /// the current host automatically, but `AsyncImage` needs an absolute URL.
    /// Absolute URLs are still limited to http(s), and arbitrary schemes or
    /// unrecognised relative paths are rejected.
    static func assetURL(_ raw: String?) -> URL? {
        guard let raw = raw?.trimmingCharacters(in: .whitespacesAndNewlines), !raw.isEmpty else {
            return nil
        }
        if let url = URL(string: raw), isSafe(url) {
            return url
        }
        guard raw.hasPrefix("/"),
              let origin = URL(string: APIClient.shared.assetOrigin),
              let resolved = URL(string: raw, relativeTo: origin)?.absoluteURL,
              isSafe(resolved) else {
            return nil
        }
        return resolved
    }
}
