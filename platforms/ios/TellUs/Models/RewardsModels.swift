import Foundation

// Mirrors client/tellus/src/api/types.ts:199-244.

struct PointsBalance: Codable {
    let account_id: String
    let points_balance: Int
    let lifetime_points: Int
    let level: Int
    let current_streak: Int
    let longest_streak: Int
    let last_activity_date: String?
    let points_to_next_level: Int
    let level_floor: Int
    let level_ceiling: Int

    /// Level curve threshold(L) = 50·L·(L-1) is computed server-side; the
    /// client only renders progress within the current level's span.
    var levelProgress: Double {
        let span = level_ceiling - level_floor
        guard span > 0 else { return 1 }
        return Double(lifetime_points - level_floor) / Double(span)
    }
}

struct LedgerEntry: Codable, Identifiable {
    let id: String
    let delta: Int
    let balance_after: Int
    /// Open set: earn_feedback | earn_engagement | earn_grant | redeem | adjustment.
    let reason: String
    let reference_type: String?
    let reference_id: String?
    let description: String?
    let created_at: String
}

struct BadgeItem: Codable, Identifiable {
    let key: String
    let name: String
    let description: String?
    let icon: String?
    let earned: Bool
    let awarded_at: String?
    var id: String { key }
}

struct Listing: Codable, Identifiable {
    let id: String
    let brand_id: String?
    let brand_name: String?
    let city: String?
    let state: String?
    let title: String
    let description: String?
    let image_url: String?
    let points_cost: Int
    let quantity_total: Int?
    let quantity_claimed: Int
    let quantity_remaining: Int?
    let redemption_type: RedemptionType
    let terms: String?
    let active_from: String?
    let active_to: String?
    let is_active: Bool
    let created_at: String
    let expiry_days: Int
    let visibility: ListingVisibility
    let like_count: Int?
    let liked_by_me: Bool?
    var likeCount: Int { like_count ?? 0 }
    var likedByMe: Bool { liked_by_me ?? false }
}

struct Redemption: Codable, Identifiable {
    let id: String
    let account_id: String
    let listing_id: String
    let listing_title: String?
    let brand_name: String?
    let listing_city: String?
    let listing_state: String?
    let points_spent: Int
    let status: RedemptionStatus
    /// TU-XXXXXXXX for code/qr redemption types.
    let code: String?
    let issued_at: String?
    let redeemed_at: String?
    let expires_at: String?
    let created_at: String
}

struct RedeemRequest: Encodable { let listing_id: String }
