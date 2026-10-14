import Foundation
import Observation

@Observable @MainActor
final class SalesWorkspaceModel {
    var campaigns: [SalesCampaign] = []
    var workspaceCampaigns: [SalesWorkspaceCampaign] = []
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
            struct List: Decodable { let campaigns: [SalesCampaign]; let workspace_campaigns: [SalesWorkspaceCampaign]? }
            let list: List = try await client.request(method: "GET", path: "/matcha-work/projects/\(projectId)/sales")
            try Task.checkCancellation()
            campaigns = list.campaigns
            workspaceCampaigns = list.workspace_campaigns ?? []
            if let id = selectedId, !campaigns.contains(where: { $0.id == id }) { selectedId = nil; snapshot = nil }
            if selectedId == nil { selectedId = campaigns.first?.id }
            if let id = selectedId {
                let loaded: SalesSnapshot = try await client.request(method: "GET", path: "/matcha-work/sales/\(id)")
                try Task.checkCancellation()
                if selectedId == id { snapshot = loaded }
            } else { snapshot = nil }
            if selected == selectedId { error = nil }
        } catch is CancellationError { } catch { report(error) }
    }
    /// The 15-second poll. Reads only statuses and fingerprints, and reloads the
    /// full campaign (every draft's text) only when one of them changed.
    func poll() async {
        guard let id = selectedId, let current = snapshot else { return await refresh() }
        do {
            let status: SalesStatus = try await client.request(method: "GET", path: "/matcha-work/sales/\(id)/status")
            try Task.checkCancellation()
            guard selectedId == id else { return }
            if Self.changed(current, status) { await refresh() }
        } catch is CancellationError { } catch { report(error) }
    }
    nonisolated static func changed(_ snapshot: SalesSnapshot, _ status: SalesStatus) -> Bool {
        let before = snapshot.prospects.map { "\($0.id)|\($0.status)|\($0.review_token)|\($0.error ?? "")" }
        let after = status.prospects.map { "\($0.id)|\($0.status)|\($0.review_token)|\($0.error ?? "")" }
        return before != after || snapshot.counts != status.counts
            || snapshot.campaign.status != status.campaign.status
            || snapshot.campaign.error != status.campaign.error
            || snapshot.campaign.footer != status.campaign.footer
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
    func create(title: String, target: String, offer: String, footer: String, requestId: UUID) async throws {
        struct Body: Encodable { let request_id: UUID; let title: String; let target: String; let offer: String; let footer: String }
        let campaign: SalesCampaign = try await client.request(method: "POST", path: "/matcha-work/projects/\(projectId)/sales", body: Body(request_id: requestId, title: title, target: target, offer: offer, footer: footer))
        selectedId = campaign.id
    }
    func updateCampaign(title: String, target: String, offer: String, footer: String, campaignId: String) async throws {
        struct Body: Encodable { let title: String; let target: String; let offer: String; let footer: String }
        let _: SalesCampaign = try await client.request(method: "PATCH", path: "/matcha-work/sales/\(campaignId)", body: Body(title: title, target: target, offer: offer, footer: footer))
    }
    func deleteCampaign(_ campaignId: String) async throws {
        let _: [String: Bool] = try await client.request(method: "DELETE", path: "/matcha-work/sales/\(campaignId)")
        if selectedId == campaignId { selectedId = nil; snapshot = nil }
    }
    func importContacts(_ contacts: [SalesContact], campaignId: String) async throws {
        struct Body: Encodable { let prospects: [SalesContact] }
        let result: [String: Int] = try await client.request(method: "POST", path: "/matcha-work/sales/\(campaignId)/prospects", body: Body(prospects: contacts))
        var parts = ["Added \(result["added", default: 0]) prospects", "skipped \(result["duplicates", default: 0]) duplicates"]
        if let suppressed = result["suppressed"], suppressed > 0 { parts.append("\(suppressed) marked Do not contact") }
        notice = parts.joined(separator: "; ") + "."
    }
    func template(subject: String, body: String, campaignId: String) async throws {
        struct Body: Encodable { let subject: String; let body: String }
        let _: [String: Int] = try await client.request(method: "POST", path: "/matcha-work/sales/\(campaignId)/template", body: Body(subject: subject, body: body))
    }
    func edit(_ item: SalesProspect, email: String, subject: String, body: String, stage: String, campaignId: String) async throws {
        struct Body: Encodable { let email: String?; let subject: String?; let body: String?; let stage: String; let review_token: String }
        let _: SalesProspect = try await client.request(method: "PATCH", path: "/matcha-work/sales/\(campaignId)/prospects/\(item.id)", body: Body(email: item.editable ? email : nil, subject: item.editable ? subject : nil, body: item.editable ? body : nil, stage: stage, review_token: item.review_token))
    }
    func optOut(_ item: SalesProspect, campaignId: String) async throws {
        let _: SalesProspect = try await client.request(method: "POST", path: "/matcha-work/sales/\(campaignId)/prospects/\(item.id)/opt-out")
    }
    func deleteProspect(_ item: SalesProspect, campaignId: String) async throws {
        let _: [String: Bool] = try await client.request(method: "DELETE", path: "/matcha-work/sales/\(campaignId)/prospects/\(item.id)")
    }
    /// After checking Gmail Sent for an unconfirmed message.
    func resolve(_ item: SalesProspect, sent: Bool, campaignId: String) async throws {
        struct Body: Encodable { let outcome: String }
        let _: SalesProspect = try await client.request(method: "POST", path: "/matcha-work/sales/\(campaignId)/prospects/\(item.id)/resolve", body: Body(outcome: sent ? "sent" : "not_sent"))
    }
    func loadSender() async {
        do { sender = try await EmailService.shared.status().email } catch { report(error) }
    }
    func send(_ items: [SalesProspect], campaignId: String, requestId: UUID) async throws {
        guard let sender else { throw SalesCSV.Invalid("Connect Gmail in Email settings first.") }
        guard items.count <= SalesBatch.limit else { throw SalesCSV.Invalid("Review at most \(SalesBatch.limit) messages at a time.") }
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
