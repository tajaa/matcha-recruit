import Foundation

final class LoyaltyService {
    static let shared = LoyaltyService()
    private let client = APIClient.shared
    private init() {}

    func programs() async throws -> [LoyaltyProgramSummary] {
        try await client.request(method: "GET", path: "/me/loyalty/programs")
    }

    func program(brandID: String) async throws -> LoyaltyProgram {
        try await client.request(method: "GET", path: "/me/loyalty/programs/\(brandID)")
    }

    func memberQR(brandID: String) async throws -> LoyaltyMemberQR {
        try await client.request(method: "POST", path: "/me/loyalty/programs/\(brandID)/member-qr")
    }

    func ledger(brandID: String, limit: Int = 50, offset: Int = 0) async throws -> [LoyaltyLedgerEntry] {
        try await client.request(method: "GET", path: "/me/loyalty/programs/\(brandID)/ledger?limit=\(limit)&offset=\(offset)")
    }

    func redemptions() async throws -> [LoyaltyRedemption] {
        try await client.request(method: "GET", path: "/me/loyalty/redemptions")
    }

    func issueRedemption(brandID: String, rewardID: String, clientRequestID: String) async throws -> LoyaltyRedemption {
        struct Body: Encodable { let reward_id: String; let client_request_id: String }
        return try await client.request(
            method: "POST",
            path: "/me/loyalty/programs/\(brandID)/redemptions",
            body: Body(reward_id: rewardID, client_request_id: clientRequestID)
        )
    }

    func purchase(brandID: String, storeID: String, memberToken: String, amountCents: Int) async throws -> LoyaltyEarnResult {
        try await client.request(
            method: "POST",
            path: "/businesses/\(brandID)/stores/\(storeID)/loyalty/purchase",
            body: PurchaseBody(member_token: memberToken, amount_cents: amountCents)
        )
    }

    private struct PurchaseBody: Encodable {
        let member_token: String
        let amount_cents: Int
    }
}

struct LoyaltyEarnResult: Codable {
    let awarded: Bool
    let points: Int
    let points_balance: Int
    let lifetime_points: Int
    let tier_key: String
    let result_code: String
}
