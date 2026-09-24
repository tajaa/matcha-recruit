import Foundation

/// Schedule timestamps are UTC-encoded wall clocks by convention. Never
/// display them in the device time zone: that changes the shift an admin set.
enum WallClock {
    private static var gregorian: Calendar {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(secondsFromGMT: 0)!
        return calendar
    }

    static func date(_ iso: String) -> Date? {
        let parser = ISO8601DateFormatter()
        parser.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return parser.date(from: iso) ?? {
            parser.formatOptions = [.withInternetDateTime]
            return parser.date(from: iso)
        }()
    }

    static func label(_ iso: String, format: String) -> String {
        guard let value = date(iso) else { return iso }
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        formatter.dateFormat = format
        return formatter.string(from: value)
    }

    static func weekLabel(_ week: Date) -> String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        formatter.dateFormat = "MMM d, yyyy"
        return formatter.string(from: week)
    }

    static func today(now: Date = Date(), timeZone: TimeZone = .current) -> Date {
        var local = Calendar(identifier: .gregorian)
        local.timeZone = timeZone
        let parts = local.dateComponents([.year, .month, .day], from: now)
        return gregorian.date(from: parts)!
    }

    static func weekStart(containing day: Date, weekStartWeekday: Int = 0) -> Date {
        let calendar = gregorian
        let start = calendar.startOfDay(for: day)
        let weekday = calendar.component(.weekday, from: start) - 1
        return calendar.date(byAdding: .day, value: -((weekday - weekStartWeekday + 7) % 7), to: start)!
    }

    static func range(starting week: Date) -> (String, String) {
        let calendar = gregorian
        let startDay = calendar.startOfDay(for: week)
        let endDay = calendar.date(byAdding: .day, value: 7, to: startDay)!
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        formatter.dateFormat = "yyyy-MM-dd"
        return ("\(formatter.string(from: startDay))T00:00:00Z", "\(formatter.string(from: endDay))T00:00:00Z")
    }

    static func move(_ week: Date, by weeks: Int) -> Date {
        let calendar = gregorian
        return calendar.date(byAdding: .day, value: weeks * 7, to: week)!
    }
}
