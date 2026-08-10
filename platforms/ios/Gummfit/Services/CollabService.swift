import Foundation
final class CollabService { static let shared = CollabService(); private init() {}
    func campaigns() async throws -> [CollabCampaign] { try await APIClient.shared.request(method: "GET", path: "/collab/campaigns") }
    func createCampaign(_ body: CollabCampaignCreate) async throws -> CollabCampaign { try await APIClient.shared.request(method: "POST", path: "/collab/campaigns", body: body) }
    func createOffer(_ body: OfferCreate) async throws -> OfferDetail { try await APIClient.shared.request(method: "POST", path: "/collab/offers", body: body) }
    func offers() async throws -> OfferPage { try await APIClient.shared.request(method: "GET", path: "/collab/offers") }
    func offer(_ id: String) async throws -> OfferDetail { try await APIClient.shared.request(method: "GET", path: "/collab/offers/\(id)") }
    func accept(_ id: String) async throws -> OfferDetail { try await APIClient.shared.request(method: "POST", path: "/collab/offers/\(id)/accept") }
    func counter(_ id: String, terms: CollabTerms, message: String?) async throws -> OfferDetail { try await APIClient.shared.request(method: "POST", path: "/collab/offers/\(id)/counter", body: OfferCounter(terms: terms, message: message)) }
    func decline(_ id: String, reason: String?) async throws -> OfferDetail { try await APIClient.shared.request(method: "POST", path: "/collab/offers/\(id)/decline", body: OfferDecline(reason: reason)) }
    func withdraw(_ id: String) async throws -> OfferDetail { try await APIClient.shared.request(method: "POST", path: "/collab/offers/\(id)/withdraw") }
    func cancel(_ id: String, reason: String) async throws -> OfferDetail { try await APIClient.shared.request(method: "POST", path: "/collab/offers/\(id)/cancel", body: OfferCancel(reason: reason)) }
    func message(_ id: String, _ body: String) async throws -> OfferMessage { try await APIClient.shared.request(method: "POST", path: "/collab/offers/\(id)/messages", body: OfferMessageCreate(body: body)) }
    func submit(_ id: String, deliverableId: String, body: DeliverableSubmit) async throws -> Deliverable { try await APIClient.shared.request(method: "POST", path: "/collab/offers/\(id)/deliverables/\(deliverableId)/submit", body: body) }
    func approve(_ id: String, deliverableId: String) async throws -> OfferDetail { try await APIClient.shared.request(method: "POST", path: "/collab/offers/\(id)/deliverables/\(deliverableId)/approve") }
    func requestRevision(_ id: String, deliverableId: String, note: String) async throws -> Deliverable { try await APIClient.shared.request(method: "POST", path: "/collab/offers/\(id)/deliverables/\(deliverableId)/request-revision", body: DeliverableRevision(review_note: note)) }
    func nudgePayment(_ id: String, paymentId: String) async throws { try await APIClient.shared.requestVoid(method: "POST", path: "/collab/offers/\(id)/payments/\(paymentId)/nudge") }
}
