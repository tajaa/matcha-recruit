import Foundation

enum RequestService {
    private static let root = "/v1/portal/me/schedule"

    static func requests() async throws -> [ScheduleRequest] {
        let response: RequestsResponse = try await APIClient.shared.request(method: "GET", path: "\(root)/requests")
        return response.requests
    }

    static func offers() async throws -> [ScheduleRequest] {
        let response: OffersResponse = try await APIClient.shared.request(method: "GET", path: "\(root)/offers")
        return response.offers
    }

    static func coworkers() async throws -> [Coworker] {
        let response: CoworkersResponse = try await APIClient.shared.request(method: "GET", path: "\(root)/coworkers")
        return response.employees
    }

    static func create(_ body: ScheduleRequestBody) async throws {
        _ = try await APIClient.shared.requestData(method: "POST", path: "\(root)/requests", body: body)
    }

    static func accept(_ offer: ScheduleRequest) async throws {
        _ = try await APIClient.shared.requestData(
            method: "POST", path: "\(root)/requests/\(offer.id)/accept",
            body: AcceptOfferBody(counter_shift_id: offer.request_type == "swap" ? offer.counter_shift_id : nil)
        )
    }

    static func cancel(_ request: ScheduleRequest) async throws {
        _ = try await APIClient.shared.requestData(method: "DELETE", path: "\(root)/requests/\(request.id)")
    }

    static func withdraw(_ request: ScheduleRequest) async throws {
        _ = try await APIClient.shared.requestData(method: "POST", path: "\(root)/requests/\(request.id)/withdraw")
    }

    static func availability() async throws -> AvailabilityResponse {
        try await APIClient.shared.request(method: "GET", path: "\(root)/availability")
    }

    static func requestAvailability(_ body: AvailabilityChangeBody) async throws {
        _ = try await APIClient.shared.requestData(method: "POST", path: "\(root)/availability-requests", body: body)
    }

    static func pto() async throws -> PTOSummary {
        try await APIClient.shared.request(method: "GET", path: "/v1/portal/me/pto")
    }

    static func requestPTO(_ body: PTORequestBody) async throws {
        _ = try await APIClient.shared.requestData(method: "POST", path: "/v1/portal/me/pto/request", body: body)
    }

    static func cancelPTO(_ id: String) async throws {
        _ = try await APIClient.shared.requestData(method: "DELETE", path: "/v1/portal/me/pto/request/\(id)")
    }
}
