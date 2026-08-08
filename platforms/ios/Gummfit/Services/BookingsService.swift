import Foundation

/// Booking types, availability, bookings, rate rules, rider, and the unified
/// pending-requests queue (server/app/cappe/routes/bookings.py, rider.py).
final class BookingsService {
    static let shared = BookingsService()
    private init() {}

    // MARK: Booking types

    func listTypes(siteId: String, locationId: String? = nil, shared: Bool = false) async throws -> [CappeBookingType] {
        try await APIClient.shared.request(method: "GET", path: "/sites/\(siteId)/booking-types" + LocationQuery.string(locationId, shared: shared))
    }

    func createType(siteId: String, _ body: CappeBookingTypeCreate) async throws -> CappeBookingType {
        try await APIClient.shared.request(method: "POST", path: "/sites/\(siteId)/booking-types", body: body)
    }

    func updateType(siteId: String, typeId: String, _ body: CappeBookingTypeUpdate) async throws -> CappeBookingType {
        try await APIClient.shared.request(method: "PUT", path: "/sites/\(siteId)/booking-types/\(typeId)", body: body)
    }

    func deleteType(siteId: String, typeId: String) async throws {
        try await APIClient.shared.requestVoid(method: "DELETE", path: "/sites/\(siteId)/booking-types/\(typeId)")
    }

    // MARK: Availability (whole-schedule replace, per location)

    func getAvailability(siteId: String, locationId: String? = nil, shared: Bool = false) async throws -> [CappeAvailability] {
        try await APIClient.shared.request(method: "GET", path: "/sites/\(siteId)/availability" + LocationQuery.string(locationId, shared: shared))
    }

    /// Replaces the weekly availability FOR ONE LOCATION (nil = shared/all) —
    /// other locations untouched.
    func replaceAvailability(siteId: String, locationId: String? = nil, _ slots: [CappeAvailabilitySlot]) async throws -> [CappeAvailability] {
        try await APIClient.shared.request(
            method: "PUT",
            path: "/sites/\(siteId)/availability" + LocationQuery.string(locationId),
            body: CappeAvailabilityReplace(slots: slots)
        )
    }

    // MARK: Bookings

    func list(siteId: String) async throws -> [CappeBooking] {
        try await APIClient.shared.request(method: "GET", path: "/sites/\(siteId)/bookings")
    }

    func setStatus(siteId: String, bookingId: String, status: String) async throws -> CappeBooking {
        try await APIClient.shared.request(
            method: "PATCH", path: "/sites/\(siteId)/bookings/\(bookingId)",
            body: CappeBookingStatusUpdate(status: status)
        )
    }

    func accept(siteId: String, bookingId: String) async throws -> CappeBooking {
        try await APIClient.shared.request(method: "POST", path: "/sites/\(siteId)/bookings/\(bookingId)/accept")
    }

    func decline(siteId: String, bookingId: String, reason: String? = nil) async throws -> CappeBooking {
        try await APIClient.shared.request(
            method: "POST", path: "/sites/\(siteId)/bookings/\(bookingId)/decline",
            body: CappeApprovalDecline(reason: reason)
        )
    }

    func requests(siteId: String) async throws -> [CappeRequestSummary] {
        try await APIClient.shared.request(method: "GET", path: "/sites/\(siteId)/requests")
    }

    // MARK: Rate rules

    func rateRules(siteId: String, locationId: String? = nil, shared: Bool = false) async throws -> [CappeRateRule] {
        try await APIClient.shared.request(method: "GET", path: "/sites/\(siteId)/rate-rules" + LocationQuery.string(locationId, shared: shared))
    }

    func replaceRateRules(siteId: String, locationId: String? = nil, _ rules: [CappeRateRuleInput]) async throws -> [CappeRateRule] {
        try await APIClient.shared.request(
            method: "PUT",
            path: "/sites/\(siteId)/rate-rules" + LocationQuery.string(locationId),
            body: CappeRateRulesReplace(rules: rules)
        )
    }

    // MARK: Rider (Pro, personal creators only — 403/402 surface as ordinary APIError)

    func rider(siteId: String) async throws -> [CappeRiderItem] {
        try await APIClient.shared.request(method: "GET", path: "/sites/\(siteId)/rider")
    }

    func replaceRider(siteId: String, _ items: [CappeRiderItemInput]) async throws -> [CappeRiderItem] {
        try await APIClient.shared.request(method: "PUT", path: "/sites/\(siteId)/rider", body: CappeRiderReplace(items: items))
    }
}
