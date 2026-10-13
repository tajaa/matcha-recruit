import Foundation
import Observation

@Observable @MainActor
final class SalesWorkspaceModel {
    var campaigns: [SalesCampaign] = []
    var snapshot: SalesSnapshot?
    var selectedId: String?
    var busy = false
    var error: String?
    var notice: String?
    var sender: String?
    private let client = APIClient.shared
    private let projectId: String
    init(projectId: String) { self.projectId = projectId }

    func refresh() async {
        let selected = selectedId
        do {
            struct List: Decodable { let campaigns: [SalesCampaign] }
            let list: List = try await client.request(method: "GET", path: "/matcha-work/projects/\(projectId)/sales")
            try Task.checkCancellation()
            campaigns = list.campaigns
            if selectedId == nil { selectedId = campaigns.first?.id }
            if let id = selectedId {
                let loaded: SalesSnapshot = try await client.request(method: "GET", path: "/matcha-work/sales/\(id)")
                try Task.checkCancellation()
                if selectedId == id { snapshot = loaded }
            } else { snapshot = nil }
            if selected == selectedId { error = nil }
        } catch is CancellationError { } catch { report(error) }
    }
    func select(_ id: String) async {
        selectedId = id; snapshot = nil; notice = nil
        await refresh()
    }
    func perform(_ action: () async throws -> Void) async {
        guard !busy else { return }
        busy = true; error = nil
        defer { busy = false }
        do { try await action(); await refresh() } catch { report(error) }
    }
    func create(title: String, target: String, offer: String, requestId: UUID) async throws {
        struct Body: Encodable { let request_id: UUID; let title: String; let target: String; let offer: String }
        let campaign: SalesCampaign = try await client.request(method: "POST", path: "/matcha-work/projects/\(projectId)/sales", body: Body(request_id: requestId, title: title, target: target, offer: offer))
        selectedId = campaign.id
    }
    func importContacts(_ contacts: [SalesContact], campaignId: String) async throws {
        struct Body: Encodable { let prospects: [SalesContact] }
        let result: [String: Int] = try await client.request(method: "POST", path: "/matcha-work/sales/\(campaignId)/prospects", body: Body(prospects: contacts))
        notice = "Added \(result["added", default: 0]) prospects; skipped \(result["duplicates", default: 0]) duplicates."
    }
    func template(subject: String, body: String, campaignId: String) async throws {
        struct Body: Encodable { let subject: String; let body: String }
        let _: [String: Int] = try await client.request(method: "POST", path: "/matcha-work/sales/\(campaignId)/template", body: Body(subject: subject, body: body))
    }
    func edit(_ item: SalesProspect, email: String, subject: String, body: String, stage: String, campaignId: String) async throws {
        struct Body: Encodable { let email: String?; let subject: String?; let body: String?; let stage: String; let review_token: String }
        let _: SalesProspect = try await client.request(method: "PATCH", path: "/matcha-work/sales/\(campaignId)/prospects/\(item.id)", body: Body(email: item.editable ? email : nil, subject: item.editable ? subject : nil, body: item.editable ? body : nil, stage: stage, review_token: item.review_token))
    }
    func loadSender() async {
        do { sender = try await EmailService.shared.status().email } catch { report(error) }
    }
    func send(_ items: [SalesProspect], campaignId: String, requestId: UUID) async throws {
        guard let sender else { throw SalesCSV.Invalid("Connect Gmail in Email settings first.") }
        struct Draft: Encodable { let id: String; let review_token: String }
        struct Body: Encodable { let request_id: UUID; let sender: String; let drafts: [Draft] }
        let _: [String: String] = try await client.request(method: "POST", path: "/matcha-work/sales/\(campaignId)/send", body: Body(request_id: requestId, sender: sender, drafts: items.map { Draft(id: $0.id, review_token: $0.review_token) }))
    }
    func action(_ action: String, campaignId: String) async throws {
        struct Body: Encodable { let action: String }
        let _: [String: String] = try await client.request(method: "POST", path: "/matcha-work/sales/\(campaignId)/action", body: Body(action: action))
    }
    func report(_ error: Error) {
        self.error = (error as? APIError).map { AssistantText.message(for: $0) } ?? error.localizedDescription
    }
}
