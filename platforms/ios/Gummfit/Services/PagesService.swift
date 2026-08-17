import Foundation

final class PagesService {
    static let shared = PagesService()
    private init() {}

    func list(siteId: String) async throws -> [CappePage] {
        try await APIClient.shared.request(method: "GET", path: "/sites/\(siteId)/pages")
    }

    func create(siteId: String, _ body: CappePageCreate) async throws -> CappePage {
        try await APIClient.shared.request(method: "POST", path: "/sites/\(siteId)/pages", body: body)
    }

    func update(siteId: String, pageId: String, _ body: CappePageUpdate) async throws -> CappePage {
        try await APIClient.shared.request(method: "PUT", path: "/sites/\(siteId)/pages/\(pageId)", body: body)
    }

    func delete(siteId: String, pageId: String) async throws {
        try await APIClient.shared.requestVoid(method: "DELETE", path: "/sites/\(siteId)/pages/\(pageId)")
    }
}
