import Foundation
final class MarketingService { static let shared = MarketingService(); private init() {}
    func subscribers(_ siteId: String) async throws -> [CappeSubscriber] { try await APIClient.shared.request(method: "GET", path: "/sites/\(siteId)/subscribers") }
    func addSubscriber(_ siteId: String, _ body: CappeSubscriberCreate) async throws -> CappeSubscriber { try await APIClient.shared.request(method: "POST", path: "/sites/\(siteId)/subscribers", body: body) }
    func deleteSubscriber(_ siteId: String, _ id: String) async throws { try await APIClient.shared.requestVoid(method: "DELETE", path: "/sites/\(siteId)/subscribers/\(id)") }
    func campaigns(_ siteId: String) async throws -> [CappeCampaign] { try await APIClient.shared.request(method: "GET", path: "/sites/\(siteId)/campaigns") }
    func createCampaign(_ siteId: String, _ body: CappeCampaignCreate) async throws -> CappeCampaign { try await APIClient.shared.request(method: "POST", path: "/sites/\(siteId)/campaigns", body: body) }
    func updateCampaign(_ siteId: String, _ id: String, _ body: CappeCampaignUpdate) async throws -> CappeCampaign { try await APIClient.shared.request(method: "PUT", path: "/sites/\(siteId)/campaigns/\(id)", body: body) }
    func deleteCampaign(_ siteId: String, _ id: String) async throws { try await APIClient.shared.requestVoid(method: "DELETE", path: "/sites/\(siteId)/campaigns/\(id)") }
    func sendCampaign(_ siteId: String, _ id: String) async throws -> CappeCampaign { try await APIClient.shared.request(method: "POST", path: "/sites/\(siteId)/campaigns/\(id)/send") }
    func forms(_ siteId: String) async throws -> [CappeForm] { try await APIClient.shared.request(method: "GET", path: "/sites/\(siteId)/forms") }
    func createForm(_ siteId: String, _ body: CappeFormCreate) async throws -> CappeForm { try await APIClient.shared.request(method: "POST", path: "/sites/\(siteId)/forms", body: body) }
    func updateForm(_ siteId: String, _ id: String, _ body: CappeFormUpdate) async throws -> CappeForm { try await APIClient.shared.request(method: "PUT", path: "/sites/\(siteId)/forms/\(id)", body: body) }
    func deleteForm(_ siteId: String, _ id: String) async throws { try await APIClient.shared.requestVoid(method: "DELETE", path: "/sites/\(siteId)/forms/\(id)") }
    func submissions(_ siteId: String, _ formId: String) async throws -> [CappeFormSubmission] { try await APIClient.shared.request(method: "GET", path: "/sites/\(siteId)/forms/\(formId)/submissions") }
    func markRead(_ siteId: String, _ formId: String, _ submissionId: String) async throws -> CappeFormSubmission { try await APIClient.shared.request(method: "PATCH", path: "/sites/\(siteId)/forms/\(formId)/submissions/\(submissionId)") }
    func deleteSubmission(_ siteId: String, _ formId: String, _ id: String) async throws { try await APIClient.shared.requestVoid(method: "DELETE", path: "/sites/\(siteId)/forms/\(formId)/submissions/\(id)") }
    func posts(_ siteId: String) async throws -> [CappePost] { try await APIClient.shared.request(method: "GET", path: "/sites/\(siteId)/posts") }
    func createPost(_ siteId: String, _ body: CappePostCreate) async throws -> CappePost { try await APIClient.shared.request(method: "POST", path: "/sites/\(siteId)/posts", body: body) }
    func updatePost(_ siteId: String, _ id: String, _ body: CappePostUpdate) async throws -> CappePost { try await APIClient.shared.request(method: "PUT", path: "/sites/\(siteId)/posts/\(id)", body: body) }
    func deletePost(_ siteId: String, _ id: String) async throws { try await APIClient.shared.requestVoid(method: "DELETE", path: "/sites/\(siteId)/posts/\(id)") }
}
