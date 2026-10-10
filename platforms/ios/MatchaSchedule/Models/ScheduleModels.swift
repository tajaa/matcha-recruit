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
    /// Only for an employee: crew and store managers.
    let profile: EmployeeProfile?
    /// Only for a business admin, whose /auth/me profile has another shape.
    let business: BusinessProfile?

    private enum CodingKeys: String, CodingKey { case user, profile }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        user = try container.decode(AuthUser.self, forKey: .user)
        if user.role == "employee" {
            profile = try container.decodeIfPresent(EmployeeProfile.self, forKey: .profile)
            business = nil
        } else {
            profile = nil
            business = try? container.decodeIfPresent(BusinessProfile.self, forKey: .profile)
        }
    }
}

/// The parts of a business admin's profile the app shows.
struct BusinessProfile: Decodable {
    let name: String?
    let company_name: String?
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
    // Manager reads only (`/employee-schedule/week`); absent on crew feeds.
    let job_id: String?
    let required_staff: Int?
    let published_at: String?

    var title: String { role?.isEmpty == false ? role! : "Shift" }

    /// Seats nobody fills yet; never negative, and none on a cancelled shift.
    var openSeats: Int {
        guard status != "cancelled", let required_staff else { return 0 }
        return max(0, required_staff - assignments.count)
    }
}

struct ShiftAssignment: Decodable, Identifiable {
    let employee_id: String
    let name: String
    let status: String
    /// The server already nulls a note the manager did not share, and only
    /// sends the visibility flag to managers, so presence is the signal.
    let manager_note: String?
    let planned_breaks: [PlannedBreak]?
    /// Break entitlement for this shift; only on the employee's own assignment.
    let compliance_guidance: ComplianceGuidance?

    var id: String { employee_id }
}

extension ShiftAssignment {
    private enum CodingKeys: String, CodingKey {
        case employee_id, name, status, manager_note, planned_breaks, compliance_guidance
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        employee_id = try container.decode(String.self, forKey: .employee_id)
        name = try container.decode(String.self, forKey: .name)
        status = try container.decode(String.self, forKey: .status)
        manager_note = try container.decodeIfPresent(String.self, forKey: .manager_note)
        planned_breaks = try container.decodeIfPresent([PlannedBreak].self, forKey: .planned_breaks)
        // Guidance is an explanation beside the shift: a shape this build
        // does not know must not take the schedule down with it.
        compliance_guidance = try? container.decodeIfPresent(ComplianceGuidance.self, forKey: .compliance_guidance)
    }
}

struct ComplianceGuidance: Decodable {
    let status: String?
    let summary: String?
    let requirements: [BreakRequirement]?

    /// What the employee is entitled to, in the web portal's words.
    var entitlement: String? {
        if let summary, !summary.isEmpty { return summary }
        let active = (requirements ?? []).filter { !$0.waived }
        guard !active.isEmpty else { return nil }
        return active
            .map { "\($0.duration_minutes)-minute \($0.paid ? "paid" : "unpaid") \($0.kind) break" }
            .joined(separator: " · ")
    }

    /// The store's break rules could not be worked out for this shift.
    var needsAttention: Bool { status == "unmapped" || status == "error" }

    var mealBreakWaived: Bool {
        (requirements ?? []).contains { $0.waived && $0.kind == "meal" }
    }
}

struct BreakRequirement: Decodable {
    let kind: String
    let duration_minutes: Int
    let paid: Bool
    let waived: Bool
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
