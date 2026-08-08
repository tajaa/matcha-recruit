import Foundation

final class RewardsService {
    static let shared = RewardsService()
    private let client = APIClient.shared
    private init() {}

    /// Lazily creates the balance row server-side on first call.
    func balance() async throws -> PointsBalance {
        try await client.request(method: "GET", path: "/rewards/balance")
    }

    func ledger(limit: Int = 50, offset: Int = 0) async throws -> [LedgerEntry] {
        try await client.request(method: "GET", path: "/rewards/ledger?limit=\(limit)&offset=\(offset)")
    }

    func badges() async throws -> [BadgeItem] {
        try await client.request(method: "GET", path: "/badges")
    }

    func marketplace(city: String?) async throws -> [Listing] {
        var path = "/marketplace"
        if let city, !city.isEmpty {
            var components = URLComponents()
            components.queryItems = [URLQueryItem(name: "city", value: city)]
            path += components.percentEncodedQuery.map { "?" + $0 } ?? ""
        }
        return try await client.request(method: "GET", path: path)
    }

    /// 409 on insufficient points / sold out / inactive / outside window /
    /// board-only-and-not-a-member — caller maps `detail` to user copy.
    func redeem(listingId: String) async throws -> Redemption {
        try await client.request(method: "POST", path: "/redeem", body: RedeemRequest(listing_id: listingId))
    }

    func redemptions() async throws -> [Redemption] {
        try await client.request(method: "GET", path: "/redemptions")
    }
}
