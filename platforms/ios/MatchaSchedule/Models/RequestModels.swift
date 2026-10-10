import Foundation

struct ScheduleRequest: Decodable, Identifiable {
    let id: String
    let employee_id: String
    let employee_name: String
    let request_type: String
    let status: String
    let shift_id: String?
    let shift_starts_at: String?
    let shift_ends_at: String?
    let shift_role: String?
    let target_employee_id: String?
    let target_employee_name: String?
    let counter_shift_id: String?
    let counter_shift_starts_at: String?
    let counter_shift_ends_at: String?
    let counter_shift_role: String?
    let unavailable_start: String?
    let unavailable_end: String?
    let availability_effective_on: String?
    let reason: String?
    let review_notes: String?
    let created_at: String
    let can_withdraw: Bool?
    /// The store the request is at (its shift's, else the requester's).
    let location_id: String?
    /// What an availability request asks for; managers review it.
    let proposed_availability: ProposedAvailability?

    var title: String { request_type == "claim" ? "Open shift claim" : request_type.capitalized }
    var isPending: Bool { ["pending", "awaiting_counterparty", "awaiting_manager"].contains(status) }
}

struct ProposedAvailability: Decodable {
    let availability_state: String?
    let windows: [AvailabilityWindow]

    private enum CodingKeys: String, CodingKey { case availability_state, windows }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        availability_state = try container.decodeIfPresent(String.self, forKey: .availability_state)
        // A shape this build does not know must not take the request list down with it.
        windows = (try? container.decode([AvailabilityWindow].self, forKey: .windows)) ?? []
    }
}

struct RequestsResponse: Decodable { let requests: [ScheduleRequest] }
struct OffersResponse: Decodable { let offers: [ScheduleRequest] }

struct Coworker: Decodable, Identifiable {
    let id: String
    let name: String
}
struct CoworkersResponse: Decodable { let employees: [Coworker] }

struct ScheduleRequestBody: Encodable {
    let request_type: String
    let shift_id: String?
    let target_employee_id: String?
    let counter_shift_id: String?
    let unavailable_start: String?
    let unavailable_end: String?
    let reason: String?
}

struct AcceptOfferBody: Encodable { let counter_shift_id: String? }

struct AvailabilityWindow: Codable, Identifiable {
    let weekday: Int
    let start_time: String
    let end_time: String
    var id: String { "\(weekday)-\(start_time)-\(end_time)" }
}

struct AvailabilityResponse: Decodable {
    let availability_state: String?
    let windows: [AvailabilityWindow]
    let pending_request: ScheduleRequest?
}

struct AvailabilityReplaceBody: Encodable {
    let availability_state: String
    let windows: [AvailabilityWindow]
}

struct AvailabilityChangeBody: Encodable {
    let availability: AvailabilityReplaceBody
    let effective_on: String
    let reason: String?
}

struct PTOBalance: Decodable {
    let balance_hours: String
}

struct PTORequest: Decodable, Identifiable {
    let id: String
    let start_date: String
    let end_date: String
    let hours: String
    let reason: String?
    let request_type: String
    let status: String
    let denial_reason: String?
}

struct PTOSummary: Decodable {
    let balance: PTOBalance
    let pending_requests: [PTORequest]
    let approved_requests: [PTORequest]
}

struct PTORequestBody: Encodable {
    let start_date: String
    let end_date: String
    let hours: String
    let reason: String?
    let request_type: String
}
