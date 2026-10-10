import Foundation

/// What the signed-in account may manage (`GET /employee-schedule/manager/scope`).
/// Business admins see every store; a store manager sees their own.
struct ManagerScope: Decodable, Equatable {
    let can_manage: Bool
    let role: String
    let company_wide: Bool
    let locations: [ManagedLocation]
    let features: ManagerFeatures
    let pending_requests: Int
}

struct ManagedLocation: Decodable, Identifiable, Equatable, Hashable {
    let id: String
    let name: String?
    let timezone: String?
    let week_start_weekday: Int

    var timeZone: TimeZone? { timezone.flatMap(TimeZone.init(identifier:)) }

    var displayName: String {
        if let name, !name.trimmingCharacters(in: .whitespaces).isEmpty { return name }
        return "Store"
    }
}

struct ManagerFeatures: Decodable, Equatable {
    let huume: Bool
    let matcha_work: Bool
    let time_off: Bool

    /// The schedule assistant needs both.
    var assistant: Bool { huume && matcha_work }
}

struct RequestReviewBody: Encodable {
    let decision: String
    let review_notes: String?
    let force: Bool
}

/// A paid time off request as a business admin reviews it (`/employees/pto/requests`).
struct PTOAdminRequest: Decodable, Identifiable {
    let id: String
    let employee_id: String
    let employee_name: String
    let start_date: String
    let end_date: String
    let hours: Double
    let reason: String?
    let request_type: String
    let status: String
    let created_at: String

    var datesLine: String {
        start_date == end_date
            ? DateInput.display(start_date)
            : "\(DateInput.display(start_date)) – \(DateInput.display(end_date))"
    }

    var hoursLine: String {
        let rounded = (hours * 100).rounded() / 100
        let text = rounded == rounded.rounded() ? String(Int(rounded)) : String(rounded)
        return "\(text) hour\(rounded == 1 ? "" : "s")"
    }

    var kindLabel: String {
        switch request_type {
        case "vacation": "Vacation"
        case "sick": "Sick time"
        case "personal": "Personal time"
        default: request_type.replacingOccurrences(of: "_", with: " ").capitalized
        }
    }
}

struct PTODecisionBody: Encodable {
    let action: String
    let denial_reason: String?
}

// MARK: - The week a manager runs

struct ManagerWeek: Decodable {
    let week_start: String
    let location_id: String
    let shifts: [ScheduleShift]
    let roster: [RosterMember]
    let summary: WeekSummary
}

struct RosterMember: Decodable, Identifiable, Hashable {
    let id: String
    let name: String
    let job_title: String?
    /// Jobs this person is qualified for today.
    let job_ids: [String]
}

struct WeekSummary: Decodable, Equatable {
    let total_shifts: Int
    let published: Int
    let draft: Int
    let open_shifts: Int
    let assigned: Int
}

struct ScheduleJob: Decodable, Identifiable, Hashable {
    let id: String
    let name: String
    let location_id: String?
    /// Who is qualified. Empty means anyone may work it (the server's rule).
    let employee_ids: [String]

    func qualifies(_ employeeID: String) -> Bool { employee_ids.isEmpty || employee_ids.contains(employeeID) }
}

struct JobsResponse: Decodable { let jobs: [ScheduleJob] }

struct StoreReadiness: Decodable {
    let ready_to_publish: Bool
    let message: String?
}

struct PublishWeekResult: Decodable { let published: Int }

/// What a scheduler should see about each person this week
/// (`/locations/{id}/planning-inputs`). Decoded leniently: it is guidance
/// beside the picker, and a field this build does not know must not empty it.
struct PlanningInputs: Decodable {
    let roster: [PlanningPerson]

    private enum CodingKeys: String, CodingKey { case roster }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        roster = (try? container.decode([PlanningPerson].self, forKey: .roster)) ?? []
    }

    init(roster: [PlanningPerson]) { self.roster = roster }
}

struct PlanningPerson: Decodable {
    struct Load: Decodable { let minutes: Int; let shifts: Int }
    struct Away: Decodable { let start: String; let end: String }

    let employee_id: String
    let availability_state: String?
    let time_away: [Away]
    let load: Load?

    private enum CodingKeys: String, CodingKey { case employee_id, availability_state, time_away, load }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        employee_id = try container.decode(String.self, forKey: .employee_id)
        availability_state = try? container.decodeIfPresent(String.self, forKey: .availability_state)
        time_away = (try? container.decode([Away].self, forKey: .time_away)) ?? []
        load = try? container.decodeIfPresent(Load.self, forKey: .load)
    }

    /// "18h · 3 shifts" this week.
    var loadLine: String? {
        guard let load else { return nil }
        let hours = Double(load.minutes) / 60
        let text = hours == hours.rounded() ? String(Int(hours)) : String(format: "%.1f", hours)
        return "\(text)h · \(load.shifts) shift\(load.shifts == 1 ? "" : "s")"
    }

    /// Approved time away touching this calendar day ("2026-10-12").
    func isAway(on dayKey: String) -> Bool {
        time_away.contains { String($0.start.prefix(10)) <= dayKey && dayKey <= String($0.end.prefix(10)) }
    }
}

// MARK: - Writes

struct ShiftCreateBody: Encodable {
    let job_id: String
    let starts_at: String
    let ends_at: String
    let location_id: String
    let required_staff: Int
    /// The server works out the legally required break.
    let break_mode = "auto"
    let notes: String?
}

/// Only the fields a manager changed. `notes` set to `.some(nil)` clears the
/// note: the server writes an explicit null, and leaves a missing key alone.
struct ShiftPatch: Encodable {
    var starts_at: String?
    var ends_at: String?
    var job_id: String?
    var required_staff: Int?
    var notes: String??
    var status: String?
    /// "auto" has the server set the break the law requires.
    var break_mode: String?

    private enum CodingKeys: String, CodingKey {
        case starts_at, ends_at, job_id, required_staff, notes, status, break_mode
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encodeIfPresent(starts_at, forKey: .starts_at)
        try container.encodeIfPresent(ends_at, forKey: .ends_at)
        try container.encodeIfPresent(job_id, forKey: .job_id)
        try container.encodeIfPresent(required_staff, forKey: .required_staff)
        if let notes { try container.encode(notes, forKey: .notes) }
        try container.encodeIfPresent(status, forKey: .status)
        try container.encodeIfPresent(break_mode, forKey: .break_mode)
    }
}

struct AssignBody: Encodable { let employee_id: String }

struct MoveAssignmentBody: Encodable {
    let employee_id: String
    let from_shift_id: String
    let to_shift_id: String
}

struct PublishWeekBody: Encodable {
    let start: String
    let end: String
    let location_id: String
}
