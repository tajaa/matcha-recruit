import Foundation

// Brand-admin web-parity models. Mirrors client/tellus/src/api/types.ts:63-104,281-295
// and server/app/tellus/models/tellus.py:104-235,437-515,797-808 (routes/links.py,
// prompts.py, marketplace.py, board.py).

enum RewardMode: String, Codable { case auto, manual }

struct Brand: Codable, Identifiable {
    let id: String
    let owner_account_id: String?
    let name: String
    let logo_url: String?
    let reward_mode: RewardMode
    let created_at: String
    var messaging_enabled: Bool

    enum CodingKeys: String, CodingKey {
        case id, owner_account_id, name, logo_url, reward_mode, created_at, messaging_enabled
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(String.self, forKey: .id)
        owner_account_id = try c.decodeIfPresent(String.self, forKey: .owner_account_id)
        name = try c.decode(String.self, forKey: .name)
        logo_url = try c.decodeIfPresent(String.self, forKey: .logo_url)
        reward_mode = try c.decode(RewardMode.self, forKey: .reward_mode)
        created_at = try c.decode(String.self, forKey: .created_at)
        messaging_enabled = try c.decodeIfPresent(Bool.self, forKey: .messaging_enabled) ?? false
    }
}

struct BrandUpdate: Encodable {
    let name: String?
    let reward_mode: String?
}

struct BrandPrompt: Codable, Identifiable {
    let id: String
    let prompt: String
    let position: Int
}

struct BrandPromptsUpdate: Encodable {
    struct Item: Encodable { let prompt: String }
    let prompts: [Item]   // PUT replaces the whole set, ≤5, array order = position
}

struct Store: Codable, Identifiable {
    let id: String
    let brand_id: String
    let name: String
    let address: String?
    let city: String?
    let state: String?
    let zipcode: String?
    let lat: Double?
    let lng: Double?
    let created_at: String
}

struct StoreCreate: Encodable {
    let name: String
    let address: String?
    let city: String?
    let state: String?
    let zipcode: String?
}

struct StoreUpdate: Encodable {
    let name: String?
    let address: String?
    let city: String?
    let state: String?
    let zipcode: String?
}

struct FeedbackLink: Codable, Identifiable {
    let id: String
    let brand_id: String
    let store_id: String?
    let token: String
    let label: String?
    let is_active: Bool
    let use_count: Int
    let max_uses: Int?
    let expires_at: String?
    let revoked_at: String?
    let created_at: String
    let store_name: String?
}

struct LinkCreate: Encodable {
    let store_id: String?
    let label: String?
    let max_uses: Int?
    let expires_at: String?
}

struct ListingCreate: Encodable {
    let title: String
    let description: String?
    let image_url: String?
    let points_cost: Int
    let quantity_total: Int?
    let redemption_type: String
    let terms: String?
    let city: String?
    let state: String?
    let active_from: String?
    let active_to: String?
    let is_active: Bool
    let expiry_days: Int
    let visibility: String
}

struct ListingUpdate: Encodable {
    let title: String?
    let description: String?
    let image_url: String?
    let points_cost: Int?
    let quantity_total: Int?
    let redemption_type: String?
    let terms: String?
    let city: String?
    let state: String?
    let active_from: String?
    let active_to: String?
    let is_active: Bool?
    let expiry_days: Int?
    let visibility: String?
}

struct RedemptionStatusUpdate: Encodable {
    let status: String   // "redeemed" | "cancelled" | "expired"
}

struct BrandTeamMember: Codable, Identifiable {
    let id: String
    let account_display_name: String
    let email: String
    let role: String   // owner | admin | location_manager | staff | moderator
    let created_at: String
    var can_manage_inbox: Bool

    enum CodingKeys: String, CodingKey {
        case id, account_display_name, email, role, created_at, can_manage_inbox
    }

    init(id: String, account_display_name: String, email: String, role: String,
         created_at: String = "", can_manage_inbox: Bool = false) {
        self.id = id
        self.account_display_name = account_display_name
        self.email = email
        self.role = role
        self.created_at = created_at
        self.can_manage_inbox = can_manage_inbox
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(String.self, forKey: .id)
        account_display_name = try c.decode(String.self, forKey: .account_display_name)
        email = try c.decode(String.self, forKey: .email)
        role = try c.decode(String.self, forKey: .role)
        created_at = try c.decode(String.self, forKey: .created_at)
        can_manage_inbox = try c.decodeIfPresent(Bool.self, forKey: .can_manage_inbox) ?? false
    }
}

struct TeamMemberAdd: Encodable { let email: String }

struct BillingStatus: Codable {
    let plan_status: BrandPlanStatus
    let location_count: Int
    let store_count: Int
    let price_per_location_cents: Int
    let monthly_total_cents: Int
    let price_available: Bool
}

struct BrandPricing: Codable {
    let price_per_location_cents: Int
    let min_locations: Int
    let max_locations: Int
}

struct LocationUpdateRequest: Encodable { let location_count: Int }
