import Foundation

// Mirrors server/app/tellus/models/tellus.py friends models. Property names
// intentionally remain snake_case so the API contract needs no CodingKeys.

enum FriendHandle {
    static func normalize(_ value: String) -> String {
        value.trimmingCharacters(in: .whitespacesAndNewlines)
            .trimmingCharacters(in: CharacterSet(charactersIn: "@"))
            .lowercased()
    }

    static func validate(_ value: String) -> Bool {
        let handle = normalize(value)
        guard (3...20).contains(handle.count),
              handle.allSatisfy({ $0.isNumber || $0.isLetter && $0.isASCII || $0 == "_" }),
              handle.allSatisfy({ $0.isNumber || ($0 >= "a" && $0 <= "z") || $0 == "_" }) else {
            return false
        }
        let reserved = ["admin", "administrator", "api", "anonymous", "billing", "help", "me",
                        "mod", "moderator", "null", "official", "root", "security", "staff",
                        "support", "system", "team", "tellus", "tellus_team", "undefined", "www", "you"]
        return !reserved.contains(handle) && !handle.hasPrefix("tellus") && !handle.hasPrefix("member")
    }
}

struct FriendSummary: Codable, Identifiable {
    let account_id: String
    var display_name: String
    let handle: String?
    let avatar_url: String?
    let city: String?
    let state: String?
    let level: Int
    let lifetime_points: Int
    let mutual_friend_count: Int
    var status: FriendshipStatus
    var request_id: String?
    let is_you: Bool

    var id: String { account_id }

    private enum CodingKeys: String, CodingKey {
        case account_id, display_name, handle, avatar_url, city, state, level,
             lifetime_points, mutual_friend_count, status, request_id, is_you
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        account_id = try c.decode(String.self, forKey: .account_id)
        display_name = try c.decodeIfPresent(String.self, forKey: .display_name) ?? "Someone"
        handle = try c.decodeIfPresent(String.self, forKey: .handle)
        avatar_url = try c.decodeIfPresent(String.self, forKey: .avatar_url)
        city = try c.decodeIfPresent(String.self, forKey: .city)
        state = try c.decodeIfPresent(String.self, forKey: .state)
        level = try c.decodeIfPresent(Int.self, forKey: .level) ?? 1
        lifetime_points = try c.decodeIfPresent(Int.self, forKey: .lifetime_points) ?? 0
        mutual_friend_count = try c.decodeIfPresent(Int.self, forKey: .mutual_friend_count) ?? 0
        status = try c.decodeIfPresent(FriendshipStatus.self, forKey: .status) ?? .none
        request_id = try c.decodeIfPresent(String.self, forKey: .request_id)
        is_you = try c.decodeIfPresent(Bool.self, forKey: .is_you) ?? false
    }

    init(account_id: String, display_name: String = "Someone", handle: String? = nil,
         avatar_url: String? = nil, city: String? = nil, state: String? = nil,
         level: Int = 1, lifetime_points: Int = 0, mutual_friend_count: Int = 0,
         status: FriendshipStatus = .none, request_id: String? = nil, is_you: Bool = false) {
        self.account_id = account_id; self.display_name = display_name; self.handle = handle
        self.avatar_url = avatar_url; self.city = city; self.state = state; self.level = level
        self.lifetime_points = lifetime_points; self.mutual_friend_count = mutual_friend_count
        self.status = status; self.request_id = request_id; self.is_you = is_you
    }
}

struct FriendRequest: Codable, Identifiable {
    let id: String
    let requester_account_id: String
    let addressee_account_id: String
    let status: String
    let source: String
    let created_at: String
    let decided_at: String?
    let person: FriendSummary?
    let direction: FriendRequestDirection?
}

struct FriendProfile: Codable {
    let account_id: String
    let display_name: String
    let handle: String?
    let avatar_url: String?
    let city: String?
    let state: String?
    let level: Int
    let lifetime_points: Int
    let current_streak: Int
    let friend_count: Int
    let mutual_friend_count: Int
    let friends_since: String?
    var is_friend: Bool
    let pending_request_id: String?
    let is_you: Bool
    let reviews: [PersonReview]?
    let followed_places: [FollowedPlace]?
    let badges: [[String: JSONValue]]?
    let boards: [PersonBoard]?
}

struct PersonReview: Codable, Identifiable { let id: String; let brand_id: String; let brand_name: String; let brand_slug: String?; let rating: Int?; let title: String?; let description: String?; let created_at: String; let publish_at: String?; let like_count: Int; let liked_by_me: Bool }
struct FollowedPlace: Codable, Identifiable { let slug: String; let name: String; let logo_url: String?; let city: String?; let state: String?; var id: String { slug } }
struct PersonBoard: Codable, Identifiable { let brand_slug: String; let brand_name: String; let logo_url: String?; let joined_at: String?; var id: String { brand_slug } }

struct FriendActivityItem: Codable, Identifiable {
    let id: String
    let kind: FriendActivityKind
    let actor: FriendSummary
    let happened_at: String
    let brand_id: String?
    let brand_name: String?
    let brand_slug: String?
    let rating: Int?
    let title: String?
    let body: String?
    let like_count: Int
    let liked_by_me: Bool
}

struct FriendActivityPage: Codable {
    let items: [FriendActivityItem]
    let next_cursor: String?
}

struct FriendRequestCount: Codable { let incoming: Int; let outgoing: Int }
struct FriendListPage: Codable { let entries: [FriendSummary]; let total: Int; let next_offset: Int? }
struct FriendInvite: Codable { let token: String; let share_url: String; let share_text: String; let expires_at: String? }
struct InvitePreview: Codable { let owner: FriendSummary }
struct ProfileUpdateFriends: Encodable { let profile_visibility: String?; let discoverable: Bool? }
struct FriendRequestCreate: Encodable { let account_id: String?; let handle: String?; let source: String }
struct FriendRequestResult: Codable { let id: String?; let status: String?; let person: FriendSummary?; let friend: FriendSummary? }
struct TellusHandleClaim: Encodable { let handle: String }
struct TellusHandleAvailability: Codable { let handle: String; let available: Bool; let reason: String? }
