import Foundation
import AppKit

/// Gatekeeper for handing URLs to `NSWorkspace.shared.open(...)`.
///
/// Any URL that originates from network / peer / user content (chat
/// attachments, project links, element notes, file storage URLs, channel
/// attachments) must go through here. `NSWorkspace.open` will launch ANY scheme
/// the system can handle — `file://` (opens local files / Finder), `smb://` /
/// `afp://` / `ftp://` (mounts a remote share → credential leak), `ssh://`,
/// `x-apple.systempreferences:`, arbitrary app schemes — so a malicious peer
/// could plant one in an "attachment" and have a click trigger it. We only open
/// `http`/`https` (matches the inline-journal-link check in JournalContentView).
enum SafeURL {
    private static let allowedSchemes: Set<String> = ["http", "https"]

    private static func isSafe(_ url: URL) -> Bool {
        guard let scheme = url.scheme?.lowercased() else { return false }
        return allowedSchemes.contains(scheme)
    }

    /// True if the string is a web URL safe to persist/open (used at write time,
    /// e.g. before saving a user-entered link).
    static func isAllowed(_ raw: String?) -> Bool {
        guard let raw, let url = URL(string: raw) else { return false }
        return isSafe(url)
    }

    /// Open an external URL string only if its scheme is http/https. Returns
    /// true if it opened. Silently ignores file://, smb://, and other schemes.
    @discardableResult
    static func open(_ raw: String?) -> Bool {
        guard let raw, let url = URL(string: raw), isSafe(url) else { return false }
        return NSWorkspace.shared.open(url)
    }

    /// Open a pre-parsed external URL only if its scheme is http/https.
    @discardableResult
    static func open(_ url: URL?) -> Bool {
        guard let url, isSafe(url) else { return false }
        return NSWorkspace.shared.open(url)
    }
}
