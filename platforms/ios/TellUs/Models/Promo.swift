import Foundation

// Mirrors server/app/tellus/models/promo.py and
// client/tellus/src/api/types.ts's promo section. Snake-case property names
// match the wire format directly, the same convention the rest of Models/ uses
// (no keyDecodingStrategy is configured on APIClient's decoder), and timestamps
// stay ISO strings rather than Date for the same reason.

struct PromoCard: Codable, Identifiable, Hashable {
    let id: String
    let card_token: String
    /// Path only, e.g. "/tellus/card/{token}" — prefix APIClient.webOrigin to
    /// build the URL the counter scanner reads.
    let card_url: String
    /// issued | redeemed | cancelled | expired. `expired` is DERIVED server-side
    /// at read time and never stored, so a card can change status without any
    /// write having happened.
    let status: String
    let campaign_title: String
    let reward_text: String
    let brand_name: String
    let brand_logo_url: String?
    let issued_at: String
    let expires_at: String
    let redeemed_at: String?
    let redeemed_store_name: String?

    var isRedeemable: Bool { status == "issued" }
}

struct PromoClaimResult: Codable {
    let id: String
    let card_token: String
    let card_url: String
    let status: String
    let campaign_title: String
    let reward_text: String
    let brand_name: String
    let brand_logo_url: String?
    let issued_at: String
    let expires_at: String
    let redeemed_at: String?
    let redeemed_store_name: String?
    /// False when this claim was a replay of a card the account already held —
    /// the endpoint is idempotent, so a second tap is a 200, not a conflict.
    let created: Bool

    var card: PromoCard {
        PromoCard(
            id: id, card_token: card_token, card_url: card_url, status: status,
            campaign_title: campaign_title, reward_text: reward_text,
            brand_name: brand_name, brand_logo_url: brand_logo_url,
            issued_at: issued_at, expires_at: expires_at,
            redeemed_at: redeemed_at, redeemed_store_name: redeemed_store_name
        )
    }
}

struct PromoClaimPreview: Codable, Equatable {
    let brand_name: String
    let brand_logo_url: String?
    let title: String
    let reward_text: String
    let description: String?
    let flyer_image_url: String?
    let available: Bool
    /// ok | cap_reached | cancelled | paused | not_started | ended | brand_inactive
    let reason: String
    let already_claimed: Bool
    /// Set only when the viewer is identified AND already holds a card.
    let card_token: String?
}

struct PromoCampaignStats: Codable {
    let claimed: Int
    let redeemed: Int
    let outstanding: Int
    let expired: Int
    let cancelled: Int
}

struct PromoCampaign: Codable, Identifiable, Hashable {
    let id: String
    let title: String
    let description: String?
    let reward_text: String
    let claim_token: String
    let claim_url: String
    let max_claims: Int
    /// Monotone issuance counter — cancelling a campaign invalidates its
    /// outstanding cards but never decrements this.
    let claim_count: Int
    let status: String
    let card_expiry_days: Int
    let starts_at: String?
    let ends_at: String?
    let flyer_image_url: String?
    let has_design: Bool
    let cancelled_at: String?
    let created_at: String
    let stats: PromoCampaignStats?

    static func == (lhs: PromoCampaign, rhs: PromoCampaign) -> Bool { lhs.id == rhs.id }
    func hash(into hasher: inout Hasher) { hasher.combine(id) }
}

struct PromoRedeemResult: Codable, Equatable {
    let campaign_title: String
    let reward_text: String
    let redeemed_at: String
    let store_name: String?
}

/// The structured body behind a failed redeem — `map_redeem_failure` puts the
/// context for an already-used card in `detail.extra`, and the counter needs it
/// to say *when* and *where* rather than just "no".
struct PromoErrorDetail: Codable {
    let code: String?
    let message: String?
    let redeemed_at: String?
    let redeemed_store_name: String?
}
