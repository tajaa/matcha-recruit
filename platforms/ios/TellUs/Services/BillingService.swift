import Foundation

final class BillingService {
    static let shared = BillingService()
    private let client = APIClient.shared
    private init() {}

    func status() async throws -> BillingStatus {
        try await client.request(method: "GET", path: "/billing/status")
    }

    func pricing() async throws -> BrandPricing {
        try await client.request(method: "GET", path: "/billing/pricing")
    }

    /// Sets the target store count. Stripe checkout (billing/checkout) stays
    /// a web-only flow — this only updates the target, matching web's
    /// documented semantics for already-active brands.
    func setLocations(count: Int) async throws -> BillingStatus {
        try await client.request(method: "PATCH", path: "/billing/locations", body: LocationUpdateRequest(location_count: count))
    }
}
