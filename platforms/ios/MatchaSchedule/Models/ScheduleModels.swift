import Foundation

struct AuthUser: Decodable {
    let id: String
    let email: String
    let role: String
}

struct TokenResponse: Decodable {
    let access_token: String
    let refresh_token: String
    let user: AuthUser
}

struct MeResponse: Decodable {
    let user: AuthUser
    let profile: EmployeeProfile?
}

struct EmployeeProfile: Decodable {
    let id: String
    let company_name: String
    let first_name: String
    let last_name: String
    let enabled_features: ScheduleFeatures

    var displayName: String {
        let name = "\(first_name) \(last_name)".trimmingCharacters(in: .whitespaces)
        return name.isEmpty ? "Employee" : name
    }
}

struct ScheduleFeatures: Decodable {
    let employee_schedule: Bool
    let time_off: Bool
}

struct ShiftListResponse: Decodable {
    let shifts: [ScheduleShift]
}

struct ScheduleShift: Decodable, Identifiable {
    let id: String
    let location_id: String?
    let role: String?
    let department: String?
    let starts_at: String
    let ends_at: String
    let break_minutes: Int?
    let notes: String?
    let status: String
    let assignments: [ShiftAssignment]
    let has_conflict: Bool?

    var title: String { role?.isEmpty == false ? role! : "Shift" }
}

struct ShiftAssignment: Decodable, Identifiable {
    let employee_id: String
    let name: String
    let status: String
    /// The server already nulls a note the manager did not share, and only
    /// sends the visibility flag to managers, so presence is the signal.
    let manager_note: String?
    let planned_breaks: [PlannedBreak]?

    var id: String { employee_id }
}

struct PlannedBreak: Decodable, Identifiable {
    let kind: String
    let ordinal: Int
    let start_local: String
    let duration_minutes: Int

    var id: String { "\(kind)-\(ordinal)" }
}

struct LocationsResponse: Decodable {
    let locations: [ScheduleLocation]
}

struct ScheduleLocation: Decodable, Identifiable {
    let id: String
    /// Nullable server-side: a work site can be saved without a name.
    let name: String?
    let city: String?
    /// 0 = Sunday … 6 = Saturday; the store's configured week start.
    let week_start_weekday: Int?
    /// IANA zone of the store's clock, which shift times are written in.
    let timezone: String?

    var timeZone: TimeZone? { timezone.flatMap(TimeZone.init(identifier:)) }

    var displayName: String {
        if let name, !name.trimmingCharacters(in: .whitespaces).isEmpty { return name }
        if let city, !city.trimmingCharacters(in: .whitespaces).isEmpty { return city }
        return "Your store"
    }
}
