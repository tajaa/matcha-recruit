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
    let manager_note: String?
    let manager_note_visible_to_employee: Bool?
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
    let name: String
}
