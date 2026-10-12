import Foundation

// MARK: - Wire shapes (server: routes/work/calendar.py, services/matcha_work/calendar_service.py)
//
// `start`/`end` are RFC 3339 with an offset for a timed event and
// `yyyy-MM-dd` for an all-day one, whose `end` is the LAST day (inclusive).
// Google events in the feed are already converted to that rule.

/// An event on the person's own Espresso calendar.
struct MWCalendarEvent: Codable, Identifiable, Hashable {
    let id: String
    var title: String
    var notes: String?
    var location: String?
    var allDay: Bool
    var start: String
    var end: String
    /// manual | assistant | email | journal
    let sourceKind: String
    /// For `email`, the Gmail message id.
    let sourceRef: String?
    /// For `email`, the subject it came from.
    let sourceLabel: String?

    enum CodingKeys: String, CodingKey {
        case id, title, notes, location, start, end
        case allDay = "all_day"
        case sourceKind = "source_kind"
        case sourceRef = "source_ref"
        case sourceLabel = "source_label"
    }
}

/// A to-do with a due date, from one of the person's productivity boards.
struct MWCalendarTodo: Codable, Identifiable, Hashable {
    let id: String
    let boardId: String
    let boardTitle: String
    let title: String
    var boardColumn: String
    let dueDate: String

    var isDone: Bool { boardColumn == "done" }

    enum CodingKeys: String, CodingKey {
        case id, title
        case boardId = "board_id"
        case boardTitle = "board_title"
        case boardColumn = "board_column"
        case dueDate = "due_date"
    }
}

/// A Google Calendar event, shown read-only.
struct MWGoogleCalendarEvent: Codable, Identifiable, Hashable {
    let id: String
    let title: String
    let start: String
    let end: String?
    let allDay: Bool
    let location: String?
    let link: String?
    let attendeeCount: Int?

    enum CodingKeys: String, CodingKey {
        case id, title, start, end, location, link
        case allDay = "all_day"
        case attendeeCount = "attendee_count"
    }
}

struct MWGoogleCalendarFeed: Codable, Hashable {
    /// ok | partial (more than it could load) | not_connected | needs_permission | error | skipped
    let status: String
    let events: [MWGoogleCalendarEvent]
}

struct MWCalendarFeed: Codable {
    let timezone: String?
    let events: [MWCalendarEvent]
    let todos: [MWCalendarTodo]
    let google: MWGoogleCalendarFeed
    var apple: AppleCalendarFeed? = nil
}

/// One event the email agent proposes. Nothing is saved until the person keeps it.
struct MWEmailCalendarSuggestion: Codable, Hashable {
    let title: String
    let start: String
    let end: String
    let allDay: Bool
    let location: String?
    let notes: String?

    enum CodingKeys: String, CodingKey {
        case title, start, end, location, notes
        case allDay = "all_day"
    }
}

struct MWEmailCalendarSuggestResponse: Codable {
    let emailId: String
    let subject: String?
    let events: [MWEmailCalendarSuggestion]
    /// What this email already put on the calendar.
    let existing: [MWCalendarEvent]

    enum CodingKeys: String, CodingKey {
        case subject, events, existing
        case emailId = "email_id"
    }
}

// MARK: - Dates on the wire

enum CalendarWire {
    /// A day as the server writes it, in the device calendar.
    static func dayString(_ date: Date, calendar: Calendar = .current) -> String {
        let c = calendar.dateComponents([.year, .month, .day], from: date)
        return String(format: "%04d-%02d-%02d", c.year ?? 0, c.month ?? 0, c.day ?? 0)
    }

    /// RFC 3339 in the device's zone, e.g. 2026-10-02T15:00:00-07:00.
    static func instantString(_ date: Date, timeZone: TimeZone = .current) -> String {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime]
        f.timeZone = timeZone
        return f.string(from: date)
    }

    /// Local midnight of a `yyyy-MM-dd`, or nil.
    static func day(_ raw: String, calendar: Calendar = .current) -> Date? {
        let parts = raw.prefix(10).split(separator: "-").compactMap { Int($0) }
        guard raw.count == 10, parts.count == 3 else { return nil }
        return calendar.date(from: DateComponents(year: parts[0], month: parts[1], day: parts[2]))
    }

    static func instant(_ raw: String) -> Date? {
        let fractional = ISO8601DateFormatter()
        fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return fractional.date(from: raw) ?? ISO8601DateFormatter().date(from: raw)
    }

    /// A wire value as a Date: an all-day value is that local day's midnight.
    static func date(_ raw: String, calendar: Calendar = .current) -> Date? {
        raw.count == 10 ? day(raw, calendar: calendar) : instant(raw)
    }
}


struct AppleCalendarDescriptor: Codable, Identifiable, Hashable {
    let id: String
    let title: String
    let editable: Bool
}

struct AppleCalendarEvent: Codable, Identifiable, Hashable {
    let id: String
    let calendar_id: String
    let title: String
    let start: String
    let end: String
    let all_day: Bool
    let notes: String?
    let location: String?
    let modified: String
    let editable: Bool
}

struct AppleCalendarFeed: Codable {
    let status: String
    let events: [AppleCalendarEvent]
    let synced_at: String?
}

struct AppleCalendarConfiguration: Codable {
    let user_id: String
    let connection_id: UUID
    let calendars: [AppleCalendarDescriptor]
    let destination: String
}

struct AppleCalendarAction: Decodable, Identifiable {
    struct Payload: Decodable {
        struct Fields: Decodable {
            let title: String?
            let start: String?
            let end: String?
            let notes: String?
            let location: String?
            let all_day: Bool?
        }
        let event: AppleCalendarEvent?
        let fields: Fields
    }
    let id: String
    let operation: String
    let payload: Payload
}

struct AppleCalendarStatus: Decodable {
    struct Action: Decodable, Identifiable {
        let id: String
        let operation: String
        let status: String
        let error: String?
    }
    let connected: Bool
    let connection_id: UUID?
    let calendars: [AppleCalendarDescriptor]?
    let destination: String?
    let synced_at: String?
    let actions: [Action]
}
