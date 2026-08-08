import Foundation

/// Client directory — derived roll-up of everyone who's interacted with the
/// site plus manually-managed rows (server/app/cappe/routes/clients.py). CSV
/// import is desktop-shaped and stays web-only (out of scope per the app plan).
final class ClientsService {
    static let shared = ClientsService()
    private init() {}

    func list(siteId: String) async throws -> [CappeClient] {
        try await APIClient.shared.request(method: "GET", path: "/sites/\(siteId)/clients")
    }

    /// Upsert by email.
    func upsert(siteId: String, _ body: CappeClientCreate) async throws -> CappeClient {
        try await APIClient.shared.request(method: "POST", path: "/sites/\(siteId)/clients", body: body)
    }

    /// Removes only the managed (manual/imported) row — derived touchpoints
    /// (orders, bookings, subscriptions) are untouched, so the person may
    /// still appear if they've otherwise interacted with the site.
    func delete(siteId: String, email: String) async throws {
        let encoded = email.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? email
        try await APIClient.shared.requestVoid(method: "DELETE", path: "/sites/\(siteId)/clients/\(encoded)")
    }
}
