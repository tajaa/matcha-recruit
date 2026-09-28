import Foundation

/// Schedule timestamps are UTC-encoded wall clocks by convention. Never
/// display them in the device time zone: that changes the shift an admin set.
/// Formatters are costly to build and every list row formats several dates,
/// so each configuration is built once. DateFormatter and
/// ISO8601DateFormatter are thread-safe for formatting and parsing; the lock
/// only guards the dictionary.
final class FormatterCache: @unchecked Sendable {
    static let shared = FormatterCache()
    private var formatters: [String: DateFormatter] = [:]
    private let lock = NSLock()

    func formatter(_ key: String, build: () -> DateFormatter) -> DateFormatter {
        lock.lock()
        defer { lock.unlock() }
        if let cached = formatters[key] { return cached }
        let made = build()
        formatters[key] = made
        return made
    }
}

enum WallClock {
    private static let utc = TimeZone(secondsFromGMT: 0)!
    private static let fractionalParser: ISO8601DateFormatter = {
        let parser = ISO8601DateFormatter()
        parser.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return parser
    }()
    private static let plainParser: ISO8601DateFormatter = {
        let parser = ISO8601DateFormatter()
        parser.formatOptions = [.withInternetDateTime]
        return parser
    }()

    private static var gregorian: Calendar {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = utc
        return calendar
    }

    /// A fixed-pattern formatter on the UTC clock face (shared, cached).
    static func formatter(_ pattern: String) -> DateFormatter {
        FormatterCache.shared.formatter("wall|\(pattern)") {
            let formatter = DateFormatter()
            formatter.locale = Locale(identifier: "en_US_POSIX")
            formatter.timeZone = utc
            formatter.dateFormat = pattern
            return formatter
        }
    }

    static func date(_ iso: String) -> Date? {
        fractionalParser.date(from: iso) ?? plainParser.date(from: iso)
    }

    static func label(_ iso: String, format: String) -> String {
        guard let value = date(iso) else { return iso }
        return formatter(format).string(from: value)
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
        let day = formatter("yyyy-MM-dd")
        return ("\(day.string(from: startDay))T00:00:00Z", "\(day.string(from: endDay))T00:00:00Z")
    }

    static func move(_ week: Date, by weeks: Int) -> Date {
        let calendar = gregorian
        return calendar.date(byAdding: .day, value: weeks * 7, to: week)!
    }

    /// Hour of a wall-clock instant (read in UTC, where the clock face lives).
    static func hour(of value: Date) -> Int {
        gregorian.component(.hour, from: value)
    }

    /// A clock face right now, tagged UTC like shift times, so "has it
    /// started" compares like with like. Pass the STORE's time zone: shift
    /// times are the store's clock, and a phone in another zone would
    /// otherwise be hours off. The device zone is only the fallback.
    static func now(_ instant: Date = Date(), timeZone: TimeZone = .current) -> Date {
        instant.addingTimeInterval(TimeInterval(timeZone.secondsFromGMT(for: instant)))
    }

    /// The seven days of a week, starting on `week`.
    static func days(of week: Date) -> [Date] {
        (0..<7).compactMap { gregorian.date(byAdding: .day, value: $0, to: gregorian.startOfDay(for: week)) }
    }

    /// Calendar-day key, e.g. "2026-09-23", for grouping and scroll anchors.
    static func dayKey(_ value: Date) -> String {
        let parts = gregorian.dateComponents([.year, .month, .day], from: value)
        return String(format: "%04d-%02d-%02d", parts.year ?? 0, parts.month ?? 0, parts.day ?? 0)
    }

    static func dayKey(_ iso: String) -> String {
        date(iso).map(dayKey) ?? String(iso.prefix(10))
    }

    static func format(_ value: Date, _ pattern: String) -> String {
        formatter(pattern).string(from: value)
    }

    /// "8h" or "7h 30m" between two wall-clock timestamps.
    static func duration(from start: String, to end: String) -> String? {
        guard let from = date(start), let until = date(end), until > from else { return nil }
        let minutes = Int(until.timeIntervalSince(from) / 60)
        let hours = minutes / 60, rest = minutes % 60
        return rest == 0 ? "\(hours)h" : (hours == 0 ? "\(rest)m" : "\(hours)h \(rest)m")
    }

    /// "in 25m", "in 3h 20m", "tomorrow", "in 3 days": how long until a
    /// wall-clock start. Days are CALENDAR days on the clock face, not rounded
    /// 24-hour blocks: Mon 8 PM → Wed 7 AM is "in 2 days", Mon 1 AM → Tue
    /// 11 PM is "tomorrow". A start later today, or under 12 hours away
    /// across midnight, reads in hours.
    static func countdown(to start: Date, from now: Date) -> String {
        let minutes = Int(start.timeIntervalSince(now) / 60)
        if minutes < 1 { return "starting now" }
        if minutes < 60 { return "in \(minutes)m" }
        let hours = minutes / 60
        let calendar = gregorian
        let days = calendar.dateComponents(
            [.day], from: calendar.startOfDay(for: now), to: calendar.startOfDay(for: start)
        ).day ?? 0
        if days == 0 || hours < 12 {
            return minutes % 60 == 0 || hours >= 10 ? "in \(hours)h" : "in \(hours)h \(minutes % 60)m"
        }
        return days == 1 ? "tomorrow" : "in \(days) days"
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
    private static let parser: ISO8601DateFormatter = {
        let parser = ISO8601DateFormatter()
        parser.formatOptions = [.withInternetDateTime]
        return parser
    }()

    static func date(_ iso: String) -> Date? {
        // Python emits microseconds, which ISO8601DateFormatter's fractional
        // option does not reliably parse; the fraction never matters on screen.
        let trimmed = iso.replacingOccurrences(of: #"\.\d+"#, with: "", options: .regularExpression)
        return parser.date(from: trimmed)
    }

    private static func formatter(_ key: String, timeZone: TimeZone, locale: Locale,
                                  configure: @escaping (DateFormatter) -> Void) -> DateFormatter {
        FormatterCache.shared.formatter("instant|\(key)|\(timeZone.identifier)|\(locale.identifier)") {
            let formatter = DateFormatter()
            formatter.locale = locale
            formatter.timeZone = timeZone
            configure(formatter)
            return formatter
        }
    }

    /// List-row time: "9:41 AM" today, "Yesterday", a weekday within the
    /// week, otherwise "Sep 3".
    static func short(_ iso: String, now: Date = Date(), timeZone: TimeZone = .current,
                      locale: Locale = .current) -> String {
        guard let value = date(iso) else { return "" }
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = timeZone
        if calendar.isDate(value, inSameDayAs: now) {
            return formatter("time", timeZone: timeZone, locale: locale) { $0.timeStyle = .short }
                .string(from: value)
        }
        if let yesterday = calendar.date(byAdding: .day, value: -1, to: now),
           calendar.isDate(value, inSameDayAs: yesterday) {
            return "Yesterday"
        }
        if let days = calendar.dateComponents([.day], from: value, to: now).day, days < 7 {
            return formatter("weekday", timeZone: timeZone, locale: locale) { $0.setLocalizedDateFormatFromTemplate("EEE") }
                .string(from: value)
        }
        return formatter("monthday", timeZone: timeZone, locale: locale) { $0.setLocalizedDateFormatFromTemplate("MMM d") }
            .string(from: value)
    }

    static func label(_ iso: String, timeZone: TimeZone = .current, locale: Locale = .current) -> String {
        guard let value = date(iso) else {
            return String(iso.prefix(16)).replacingOccurrences(of: "T", with: " ")
        }
        return formatter("medium", timeZone: timeZone, locale: locale) {
            $0.dateStyle = .medium
            $0.timeStyle = .short
        }
        .string(from: value)
    }
}
