import Foundation

/// The person's Espresso calendar (`/matcha-work/calendar/*`) and the email
/// agent's calendar suggestions (`/matcha-work/agent/email/calendar-suggest`).
final class CalendarService {
    static let shared = CalendarService()
    private let client = APIClient.shared
    private let basePath = "/matcha-work"

    /// Last zone reported this launch, so the PUT happens once per change.
    private var reportedTimeZone: String?

    /// The editable fields of one event. Every key is sent, so a nil
    /// location or notes clears it on update.
    struct EventFields: Encodable {
        var title: String
        var start: String
        var end: String?
        var location: String?
        var notes: String?

        enum CodingKeys: String, CodingKey { case title, start, end, location, notes }

        func encode(to encoder: Encoder) throws {
            var c = encoder.container(keyedBy: CodingKeys.self)
            try c.encode(title, forKey: .title)
            try c.encode(start, forKey: .start)
            try c.encode(end, forKey: .end)
            try c.encode(location, forKey: .location)
            try c.encode(notes, forKey: .notes)
        }
    }

    /// Values with a `+` offset must not reach the server as a space.
    private func query(_ value: String) -> String {
        var allowed = CharacterSet.alphanumerics
        allowed.insert(charactersIn: "-._~:")
        return value.addingPercentEncoding(withAllowedCharacters: allowed) ?? value
    }

    func feed(from start: Date, to end: Date, includeGoogle: Bool = true) async throws -> MWCalendarFeed {
        let s = query(CalendarWire.instantString(start))
        let e = query(CalendarWire.instantString(end))
        return try await client.request(
            method: "GET",
            path: "\(basePath)/calendar/feed?start=\(s)&end=\(e)&include_google=\(includeGoogle)"
        )
    }

    func createEvent(
        _ fields: EventFields,
        sourceKind: String = "manual",
        sourceRef: String? = nil,
        sourceLabel: String? = nil
    ) async throws -> MWCalendarEvent {
        struct Body: Encodable {
            let fields: EventFields
            let sourceKind: String
            let sourceRef: String?
            let sourceLabel: String?
            enum CodingKeys: String, CodingKey {
                case sourceKind = "source_kind", sourceRef = "source_ref", sourceLabel = "source_label"
            }
            func encode(to encoder: Encoder) throws {
                try fields.encode(to: encoder)
                var c = encoder.container(keyedBy: CodingKeys.self)
                try c.encode(sourceKind, forKey: .sourceKind)
                try c.encodeIfPresent(sourceRef, forKey: .sourceRef)
                try c.encodeIfPresent(sourceLabel, forKey: .sourceLabel)
            }
        }
        return try await client.request(
            method: "POST", path: "\(basePath)/calendar/events",
            body: Body(fields: fields, sourceKind: sourceKind, sourceRef: sourceRef, sourceLabel: sourceLabel)
        )
    }

    func updateEvent(id: String, _ fields: EventFields) async throws -> MWCalendarEvent {
        try await client.request(method: "PATCH", path: "\(basePath)/calendar/events/\(id)", body: fields)
    }

    func deleteEvent(id: String) async throws {
        _ = try await client.requestData(method: "DELETE", path: "\(basePath)/calendar/events/\(id)")
    }

    /// Tell the server the zone this Mac is in, so the assistant speaks in
    /// the person's time. Best-effort; once per launch unless it changes.
    func reportTimeZoneIfNeeded() async {
        let name = TimeZone.current.identifier
        guard name != reportedTimeZone else { return }
        struct Body: Encodable { let timezone: String }
        struct Res: Decodable { let timezone: String }
        do {
            let _: Res = try await client.request(
                method: "PUT", path: "\(basePath)/calendar/prefs", body: Body(timezone: name))
            reportedTimeZone = name
        } catch {
            // The next launch or calendar load tries again.
        }
    }

    /// The email agent reads one message and proposes events. Saves nothing.
    func suggestFromEmail(emailId: String, instructions: String?) async throws -> MWEmailCalendarSuggestResponse {
        struct Body: Encodable {
            let email_id: String
            let instructions: String?
            let timezone: String
        }
        let trimmed = instructions?.trimmingCharacters(in: .whitespacesAndNewlines)
        return try await client.request(
            method: "POST", path: "\(basePath)/agent/email/calendar-suggest",
            body: Body(email_id: emailId, instructions: (trimmed?.isEmpty ?? true) ? nil : trimmed,
                       timezone: TimeZone.current.identifier)
        )
    }
}
