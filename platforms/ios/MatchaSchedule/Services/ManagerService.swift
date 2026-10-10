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

    // MARK: The week

    /// One store's week, drafts and all, with its roster.
    static func week(location: String, starting week: Date) async throws -> ManagerWeek {
        let start = WallClock.format(week, "yyyy-MM-dd")
        return try await APIClient.shared.request(
            method: "GET", path: "\(root)/week?start=\(start)&location=\(location)", fresh: true
        )
    }

    static func jobs(location: String) async throws -> [ScheduleJob] {
        let response: JobsResponse = try await APIClient.shared.request(
            method: "GET", path: "\(root)/jobs?location=\(location)", fresh: true
        )
        return response.jobs
    }

    static func readiness(location: String) async throws -> StoreReadiness {
        try await APIClient.shared.request(method: "GET", path: "\(root)/locations/\(location)/readiness", fresh: true)
    }

    static func planningInputs(location: String, weekStart: Date) async throws -> PlanningInputs {
        let start = WallClock.format(weekStart, "yyyy-MM-dd")
        return try await APIClient.shared.request(
            method: "GET", path: "\(root)/locations/\(location)/planning-inputs?week_start=\(start)", fresh: true
        )
    }

    // MARK: Shifts

    static func createShift(_ body: ShiftCreateBody, force: Bool) async throws {
        _ = try await APIClient.shared.requestData(method: "POST", path: "\(root)/shifts?force=\(force)", body: body)
    }

    static func updateShift(_ id: String, _ patch: ShiftPatch, force: Bool) async throws {
        _ = try await APIClient.shared.requestData(method: "PUT", path: "\(root)/shifts/\(id)?force=\(force)", body: patch)
    }

    static func deleteShift(_ id: String, force: Bool) async throws {
        _ = try await APIClient.shared.requestData(method: "DELETE", path: "\(root)/shifts/\(id)?force=\(force)")
    }

    static func publishShift(_ id: String) async throws {
        _ = try await APIClient.shared.requestData(method: "POST", path: "\(root)/shifts/\(id)/publish")
    }

    /// Publishes the store's drafts that start this week.
    static func publishWeek(location: String, starting week: Date) async throws -> Int {
        let (start, end) = WallClock.range(starting: week)
        let result: PublishWeekResult = try await APIClient.shared.request(
            method: "POST", path: "\(root)/shifts/publish",
            body: PublishWeekBody(start: start, end: end, location_id: location)
        )
        return result.published
    }

    // MARK: Assignments

    static func assign(_ employeeID: String, to shiftID: String, force: Bool) async throws {
        _ = try await APIClient.shared.requestData(
            method: "POST", path: "\(root)/shifts/\(shiftID)/assignments?force=\(force)",
            body: AssignBody(employee_id: employeeID)
        )
    }

    static func unassign(_ employeeID: String, from shiftID: String, force: Bool) async throws {
        _ = try await APIClient.shared.requestData(
            method: "DELETE", path: "\(root)/shifts/\(shiftID)/assignments/\(employeeID)?force=\(force)"
        )
    }

    static func move(_ employeeID: String, from: String, to: String, force: Bool) async throws {
        _ = try await APIClient.shared.requestData(
            method: "POST", path: "\(root)/assignments/move?force=\(force)",
            body: MoveAssignmentBody(employee_id: employeeID, from_shift_id: from, to_shift_id: to)
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
