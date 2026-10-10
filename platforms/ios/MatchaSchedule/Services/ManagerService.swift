import Foundation

/// The manager side of the schedule (`/employee-schedule/*`). The server scopes
/// every call: a store manager only reaches their own stores.
enum ManagerService {
    private static let root = "/employee-schedule"

    static func scope() async throws -> ManagerScope {
        try await APIClient.shared.request(method: "GET", path: "\(root)/manager/scope", fresh: true)
    }

    /// Requests waiting for a manager, optionally at one store.
    static func requests(location: String? = nil) async throws -> [ScheduleRequest] {
        var components = URLComponents()
        components.queryItems = [URLQueryItem(name: "status", value: "awaiting_manager")]
        if let location { components.queryItems?.append(URLQueryItem(name: "location", value: location)) }
        let response: RequestsResponse = try await APIClient.shared.request(
            method: "GET", path: "\(root)/requests?\(components.percentEncodedQuery ?? "")", fresh: true
        )
        return response.requests
    }

    static func review(_ request: ScheduleRequest, approve: Bool, notes: String?, force: Bool) async throws {
        _ = try await APIClient.shared.requestData(
            method: "POST", path: "\(root)/requests/\(request.id)/review",
            body: RequestReviewBody(decision: approve ? "approved" : "denied", review_notes: notes, force: force)
        )
    }

    // MARK: Paid time off (business admins)

    static func pendingPTO() async throws -> [PTOAdminRequest] {
        try await APIClient.shared.request(method: "GET", path: "/employees/pto/requests?status=pending", fresh: true)
    }

    static func decidePTO(_ request: PTOAdminRequest, approve: Bool, denialReason: String?) async throws {
        _ = try await APIClient.shared.requestData(
            method: "PATCH", path: "/employees/pto/requests/\(request.id)",
            body: PTODecisionBody(action: approve ? "approve" : "deny", denial_reason: denialReason)
        )
    }
}
