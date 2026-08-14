import Foundation

/// Promo campaigns and QR reward cards — the consumer wallet, the public claim
/// flow, and the brand-side campaign list and counter redeem.
///
/// The brand redeem here is the in-app path (`POST /promo/redeem`): the owner's
/// own phone is the scanner, authenticated by their session, so no device token
/// is involved. The token-authenticated `/scan/{device_token}/redeem` endpoint
/// is for the web page a shared counter tablet opens, and has no iOS caller.
final class PromoService {
    static let shared = PromoService()
    private let client = APIClient.shared
    private init() {}

    // MARK: Consumer

    func myCards() async throws -> [PromoCard] {
        try await client.request(method: "GET", path: "/me/promo-cards")
    }

    func card(token: String) async throws -> PromoCard {
        try await client.request(method: "GET", path: "/me/promo-cards/\(token)")
    }

    /// Maybe-authenticated: the response's `already_claimed` / `card_token` are
    /// only populated when the caller is a signed-in consumer.
    func claimPreview(token: String) async throws -> PromoClaimPreview {
        try await client.request(method: "GET", path: "/p/\(token)")
    }

    /// Idempotent — claiming twice returns the same card with `created: false`
    /// rather than a conflict.
    func claim(token: String) async throws -> PromoClaimResult {
        try await client.request(method: "POST", path: "/p/\(token)/claim")
    }

    // MARK: Brand

    func campaigns() async throws -> [PromoCampaign] {
        try await client.request(method: "GET", path: "/promo/campaigns")
    }

    func createCampaign(_ body: PromoCampaignCreate) async throws -> PromoCampaign {
        try await client.request(method: "POST", path: "/promo/campaigns", body: body)
    }

    func campaign(id: String) async throws -> PromoCampaign {
        try await client.request(method: "GET", path: "/promo/campaigns/\(id)")
    }

    private struct RedeemBody: Encodable {
        let card_token: String
        let store_id: String?
    }

    /// Accepts a bare card token OR the full card URL — the server's
    /// `extract_card_token` handles both, so a raw camera decode goes straight
    /// through without the client having to parse it.
    func redeem(cardToken: String, storeId: String? = nil) async throws -> PromoRedeemResult {
        try await client.request(
            method: "POST", path: "/promo/redeem",
            body: RedeemBody(card_token: cardToken, store_id: storeId)
        )
    }

    // MARK: Design

    private struct DesignBody: Encodable { let design_json: FlyerDesign }

    func design(campaignId: String) async throws -> FlyerDesignEnvelope {
        try await client.request(method: "GET", path: "/promo/campaigns/\(campaignId)/design")
    }

    func saveDesign(campaignId: String, design: FlyerDesign) async throws {
        try await client.requestVoid(
            method: "PUT", path: "/promo/campaigns/\(campaignId)/design",
            body: DesignBody(design_json: design)
        )
    }
}

struct FlyerDesignEnvelope: Codable {
    let design_json: FlyerDesign?
}

struct FlyerUploadResponse: Codable, Equatable {
    let flyer_image_url: String
}

extension PromoService {
    func uploadFlyer(
        campaignId: String,
        pngData: Data,
        filename: String = "flyer.png"
    ) async throws -> FlyerUploadResponse {
        try await client.uploadMultipart(
            path: "/promo/campaigns/\(campaignId)/flyer",
            data: pngData,
            mimeType: "image/png",
            filename: filename
        )
    }
}
