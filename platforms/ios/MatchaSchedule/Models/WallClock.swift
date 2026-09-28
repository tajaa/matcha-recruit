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

    /// "12:00 PM" from a planned break's `start_local`. The server sends a
    /// local datetime ("2026-09-23T12:00:00", sometimes with the store's
    /// offset); the clock face is already the store's, so it is read straight
    /// off the string, never converted.
    static func clockTime(_ value: String) -> String {
        let time = value.split(separator: "T").last.map(String.init) ?? value
        let parts = time.prefix(5).split(separator: ":")
        guard parts.count == 2, let hour = Int(parts[0]), let minute = Int(parts[1]),
              (0..<24).contains(hour), (0..<60).contains(minute) else { return value }
        let twelve = hour % 12 == 0 ? 12 : hour % 12
        return String(format: "%d:%02d %@", twelve, minute, hour < 12 ? "AM" : "PM")
    }
}

/// Real instants — when a message was sent or a notification created. Unlike
/// shift times these are true UTC moments, shown in the device's time zone.
enum Instant {
    static func date(_ iso: String) -> Date? {
        // Python emits microseconds, which ISO8601DateFormatter's fractional
        // option does not reliably parse; the fraction never matters on screen.
        let trimmed = iso.replacingOccurrences(of: #"\.\d+"#, with: "", options: .regularExpression)
        let parser = ISO8601DateFormatter()
        parser.formatOptions = [.withInternetDateTime]
        return parser.date(from: trimmed)
    }

    static func label(_ iso: String, timeZone: TimeZone = .current, locale: Locale = .current) -> String {
        guard let value = date(iso) else {
            return String(iso.prefix(16)).replacingOccurrences(of: "T", with: " ")
        }
        let formatter = DateFormatter()
        formatter.locale = locale
        formatter.timeZone = timeZone
        formatter.dateStyle = .medium
        formatter.timeStyle = .short
        return formatter.string(from: value)
    }
}
