import Foundation

// Mirrors client/tellus/src/api/types.ts:272-280 (routes/gamification.py).
struct LeaderboardEntry: Codable, Identifiable {
    let rank: Int
    let account_id: String
    let display_name: String
    let lifetime_points: Int
    let level: Int
    let is_you: Bool
    var id: String { account_id }
}
