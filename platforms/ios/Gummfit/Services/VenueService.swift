import Foundation

/// Locations + staff CRUD (server/app/cappe/routes/locations.py, staff.py).
/// Multi-location sites only — the More screen hides this behind
/// `site.is_multi_location`.
final class VenueService {
    static let shared = VenueService()
    private init() {}

    func listLocations(siteId: String) async throws -> [CappeLocation] {
        try await APIClient.shared.request(method: "GET", path: "/sites/\(siteId)/locations")
    }

    func createLocation(siteId: String, _ body: CappeLocationCreate) async throws -> CappeLocation {
        try await APIClient.shared.request(method: "POST", path: "/sites/\(siteId)/locations", body: body)
    }

    func updateLocation(siteId: String, locationId: String, _ body: CappeLocationUpdate) async throws -> CappeLocation {
        try await APIClient.shared.request(method: "PUT", path: "/sites/\(siteId)/locations/\(locationId)", body: body)
    }

    func deleteLocation(siteId: String, locationId: String) async throws {
        try await APIClient.shared.requestVoid(method: "DELETE", path: "/sites/\(siteId)/locations/\(locationId)")
    }

    func listStaff(siteId: String) async throws -> [CappeStaff] {
        try await APIClient.shared.request(method: "GET", path: "/sites/\(siteId)/staff")
    }

    func createStaff(siteId: String, _ body: CappeStaffCreate) async throws -> CappeStaff {
        try await APIClient.shared.request(method: "POST", path: "/sites/\(siteId)/staff", body: body)
    }

    func updateStaff(siteId: String, staffId: String, _ body: CappeStaffUpdate) async throws -> CappeStaff {
        try await APIClient.shared.request(method: "PUT", path: "/sites/\(siteId)/staff/\(staffId)", body: body)
    }

    func deleteStaff(siteId: String, staffId: String) async throws {
        try await APIClient.shared.requestVoid(method: "DELETE", path: "/sites/\(siteId)/staff/\(staffId)")
    }
}
