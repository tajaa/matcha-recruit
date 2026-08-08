import Foundation

/// Shared money formatting — keyed off each record's own `currency` field
/// (several endpoints pass it explicitly for exactly this reason), never a
/// hardcoded "$" symbol.
enum Formatters {
    private static var cache: [String: NumberFormatter] = [:]

    private static func formatter(for currency: String) -> NumberFormatter {
        if let cached = cache[currency] { return cached }
        let f = NumberFormatter()
        f.numberStyle = .currency
        f.currencyCode = currency
        cache[currency] = f
        return f
    }

    static func cents(_ cents: Int?, currency: String = "USD") -> String {
        guard let cents else { return formatter(for: currency).string(from: 0) ?? "$0.00" }
        let amount = Double(cents) / 100
        return formatter(for: currency).string(from: NSNumber(value: amount)) ?? "$0.00"
    }

    /// Wire `"HH:MM:SS"` (Python `time`, server/app/cappe/models/bookings.py)
    /// round-tripped through a `DatePicker(.hourAndMinute)` — free-text
    /// "HH:MM" fields let a typo through to a 422 after Save, so
    /// `AvailabilityView`/`RateRulesView` bind through these instead.
    static func date(fromTimeString s: String) -> Date {
        let parts = s.split(separator: ":").compactMap { Int($0) }
        var comps = DateComponents()
        comps.hour = parts.count > 0 ? parts[0] : 0
        comps.minute = parts.count > 1 ? parts[1] : 0
        comps.second = 0
        return Calendar.current.date(from: comps) ?? Date()
    }

    static func timeString(from date: Date) -> String {
        let comps = Calendar.current.dateComponents([.hour, .minute], from: date)
        return String(format: "%02d:%02d:00", comps.hour ?? 0, comps.minute ?? 0)
    }
}
