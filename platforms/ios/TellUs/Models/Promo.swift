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

struct PromoCampaignCreate: Encodable, Equatable {
    let title: String
    let reward_text: String
    let description: String?
    let max_claims: Int
    let card_expiry_days: Int
    let starts_at: String?
    let ends_at: String?

    init(
        title: String,
        reward_text: String,
        description: String? = nil,
        max_claims: Int,
        card_expiry_days: Int = 30,
        starts_at: String? = nil,
        ends_at: String? = nil
    ) {
        self.title = title
        self.reward_text = reward_text
        self.description = description
        self.max_claims = max_claims
        self.card_expiry_days = card_expiry_days
        self.starts_at = starts_at
        self.ends_at = ends_at
    }
}

enum PromoCampaignValidationError: LocalizedError, Equatable {
    case titleRequired
    case titleTooLong
    case rewardRequired
    case rewardTooLong
    case descriptionTooLong
    case invalidClaimLimit
    case invalidExpiryDays
    case endDateInPast

    var errorDescription: String? {
        switch self {
        case .titleRequired: return "Enter a campaign title."
        case .titleTooLong: return "Campaign titles must be 120 characters or fewer."
        case .rewardRequired: return "Enter the reward customers will receive."
        case .rewardTooLong: return "Rewards must be 200 characters or fewer."
        case .descriptionTooLong: return "Descriptions must be 2,000 characters or fewer."
        case .invalidClaimLimit: return "Claim limit must be a whole number between 1 and 10,000."
        case .invalidExpiryDays: return "Card validity must be a whole number of days between 1 and 365."
        case .endDateInPast: return "The campaign end date must be in the future."
        }
    }
}

struct PromoCampaignDraft: Equatable {
    var title = ""
    var rewardText = ""
    var description = ""
    var maxClaims = "50"
    var expiryDays = "30"
    var hasEndDate = false
    var endDate = Date().addingTimeInterval(86_400)

    func validated(now: Date = Date()) throws -> PromoCampaignCreate {
        let title = title.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !title.isEmpty else { throw PromoCampaignValidationError.titleRequired }
        guard title.count <= 120 else { throw PromoCampaignValidationError.titleTooLong }

        let reward = rewardText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !reward.isEmpty else { throw PromoCampaignValidationError.rewardRequired }
        guard reward.count <= 200 else { throw PromoCampaignValidationError.rewardTooLong }

        let description = description.trimmingCharacters(in: .whitespacesAndNewlines)
        guard description.count <= 2_000 else { throw PromoCampaignValidationError.descriptionTooLong }
        guard let claims = Int(maxClaims.trimmingCharacters(in: .whitespacesAndNewlines)), (1...10_000).contains(claims) else {
            throw PromoCampaignValidationError.invalidClaimLimit
        }
        guard let days = Int(expiryDays.trimmingCharacters(in: .whitespacesAndNewlines)), (1...365).contains(days) else {
            throw PromoCampaignValidationError.invalidExpiryDays
        }
        if hasEndDate, endDate <= now {
            throw PromoCampaignValidationError.endDateInPast
        }

        let iso = ISO8601DateFormatter()
        return PromoCampaignCreate(
            title: title,
            reward_text: reward,
            description: description.isEmpty ? nil : description,
            max_claims: claims,
            card_expiry_days: days,
            ends_at: hasEndDate ? iso.string(from: endDate) : nil
        )
    }
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
