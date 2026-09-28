import Foundation

enum DateInput {
    static func date(_ value: Date) -> String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = .current
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter.string(from: value)
    }

    static func time(_ value: Date) -> String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = .current
        formatter.dateFormat = "HH:mm"
        return formatter.string(from: value)
    }

    static func timeDate(_ value: String) -> Date {
        let parts = value.split(separator: ":").compactMap { Int($0) }
        let hour = parts.first ?? 9
        let minute = parts.count > 1 ? parts[1] : 0
        return Calendar.current.date(bySettingHour: hour, minute: minute, second: 0, of: Date()) ?? Date()
    }

    /// "Sep 23" from a server calendar date ("2026-09-23"); a plain calendar
    /// day, so no time zone applies. Unparseable input is returned as is.
    static func display(_ value: String, pattern: String = "MMM d") -> String {
        let parser = DateFormatter()
        parser.locale = Locale(identifier: "en_US_POSIX")
        parser.timeZone = TimeZone(secondsFromGMT: 0)
        parser.dateFormat = "yyyy-MM-dd"
        guard let day = parser.date(from: String(value.prefix(10))) else { return value }
        parser.dateFormat = pattern
        return parser.string(from: day)
    }
}
