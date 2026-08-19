import Foundation

struct LoyaltyProgramSummary: Codable, Identifiable {
    let brand_id: String
    let brand_name: String
    let brand_slug: String
    let name: String
    let point_plural: String
    let status: String
    let points_balance: Int
    let lifetime_points: Int
    let tier_key: String

    var id: String { brand_id }
}

struct LoyaltyRule: Codable, Identifiable {
    let event_key: String
    let award_type: String
    let fixed_points: Int?
    let points_per_dollar: Int?
    let min_purchase_cents: Int?
    let max_points_per_event: Int?
    let daily_cap: Int?
    let cooldown_seconds: Int?
    let is_active: Bool

    var id: String { event_key }
}

struct LoyaltyTier: Codable, Identifiable {
    let tier_key: String
    let threshold_points: Int
    let benefits: String?

    var id: String { tier_key }
}

struct LoyaltyBalance: Codable {
    let points_balance: Int
    let lifetime_points: Int
    let tier_key: String
}

struct LoyaltyReward: Codable, Identifiable {
    let id: String
    let brand_id: String
    let title: String
    let description: String?
    let terms: String?
    let points_cost: Int
    let redemption_expiry_days: Int
    let is_active: Bool
}

struct LoyaltyProgram: Codable {
    let brand_id: String
    let brand_name: String
    let brand_slug: String
    let name: String
    let point_singular: String
    let point_plural: String
    let terms: String?
    let status: String
    let counter_mode: String
    let rules: [LoyaltyRule]
    let tiers: [LoyaltyTier]
    let balance: LoyaltyBalance?
    let rewards: [LoyaltyReward]
}

struct LoyaltyMemberQR: Codable {
    let token: String
    let qr_payload: String
    let expires_at: String
}

struct LoyaltyLedgerEntry: Codable, Identifiable {
    let id: String
    let delta: Int
    let balance_after: Int
    let reason: String
    let description: String?
    let created_at: String
}

struct LoyaltyRedemption: Codable, Identifiable {
    let id: String
    let brand_id: String
    let brand_name: String
    let reward_title: String
    let points_spent: Int
    let effective_status: String
    let token: String
    let qr_payload: String
    let expires_at: String
    let redeemed_at: String?
}

struct BusinessStoreGrant: Codable, Identifiable {
    let id: String
    let name: String
    let city: String?
    let state: String?
    let status: String
}

struct BusinessMembership: Codable, Identifiable {
    let id: String
    let brand_id: String
    let brand_name: String
    let brand_slug: String
    let plan_status: String
    let role: String
    let status: String
    let all_stores: Bool
    let stores: [BusinessStoreGrant]
    let capabilities: [String]
}
