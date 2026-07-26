import Foundation

/// Shared parsing/formatting for chat timestamps. Server sends ISO-8601 strings
/// (sometimes with fractional seconds, sometimes without).
enum ChatTime {
    private static let withFraction: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f
    }()
    private static let plain: ISO8601DateFormatter = {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime]
        return f
    }()

    static func date(_ iso: String?) -> Date? {
        guard let iso else { return nil }
        return withFraction.date(from: iso) ?? plain.date(from: iso)
    }

    private static let timeOfDay: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "h:mm a"
        return f
    }()

    /// Short clock time ("3:45 PM") for a message bubble.
    static func clock(_ iso: String?) -> String {
        guard let d = date(iso) else { return "" }
        return timeOfDay.string(from: d)
    }

    /// Relative-ish label for channel-list "last message" ("now", "5m", "3h",
    /// "Mon", "Jun 3").
    static func shortRelative(_ iso: String?) -> String {
        guard let d = date(iso) else { return "" }
        let secs = Date().timeIntervalSince(d)
        if secs < 60 { return "now" }
        if secs < 3600 { return "\(Int(secs / 60))m" }
        if secs < 86_400 { return "\(Int(secs / 3600))h" }
        if secs < 7 * 86_400 {
            let f = DateFormatter(); f.dateFormat = "EEE"; return f.string(from: d)
        }
        let f = DateFormatter(); f.dateFormat = "MMM d"; return f.string(from: d)
    }
}
