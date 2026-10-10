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
