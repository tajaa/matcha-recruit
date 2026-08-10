import Foundation

/// Site CRUD + readiness/publish/directory (server/app/cappe/routes/sites.py).
/// Owns no cache of its own — AppState.sites is the single source of truth
/// for the list (small N, no meaningful cache win, and a stale cached list
/// would let the site switcher show a site that's since been renamed/deleted).
final class SitesService {
    static let shared = SitesService()
    private init() {}

    func list() async throws -> [CappeSite] {
        try await APIClient.shared.request(method: "GET", path: "/sites")
    }

    /// Always a blank site — no page editor in this app (plan §"No page editor").
    func create(name: String) async throws -> CappeSite {
        try await APIClient.shared.request(method: "POST", path: "/sites", body: CappeSiteCreate(name: name))
    }

    func readiness(siteId: String) async throws -> CappeReadiness {
        try await APIClient.shared.request(method: "GET", path: "/sites/\(siteId)/readiness")
    }
    func update(siteId: String, _ body: CappeSiteUpdate) async throws -> CappeSite { try await APIClient.shared.request(method: "PUT", path: "/sites/\(siteId)", body: body) }

    /// Throws `APIError.publishBlocked(message:missing:)` on a 422 — caller
    /// renders the checklist instead of a generic error string
    /// (server/app/cappe/routes/sites.py:365-384).
    func publish(siteId: String) async throws -> CappeSite {
        try await APIClient.shared.request(method: "POST", path: "/sites/\(siteId)/publish")
    }

    func directory(siteId: String) async throws -> CappeDirectoryListing {
        try await APIClient.shared.request(method: "GET", path: "/sites/\(siteId)/directory")
    }

    /// True PATCH — only non-nil fields on `update` are written server-side
    /// (see CappeDirectoryListingUpdate's doc comment).
    func updateDirectory(siteId: String, _ update: CappeDirectoryListingUpdate) async throws -> CappeDirectoryListing {
        try await APIClient.shared.request(method: "PUT", path: "/sites/\(siteId)/directory", body: update)
    }
}
