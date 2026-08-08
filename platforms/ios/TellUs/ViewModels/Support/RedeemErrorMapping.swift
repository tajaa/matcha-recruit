import Foundation

/// Maps the server's 409 detail text on a redeem to user-facing copy.
/// Extracted out of MarketplaceViewModel so both Marketplace and board-deal
/// redemption (RedeemFlowModel) share one mapping, and it's unit-testable
/// independent of any VM (Tests/RedeemErrorMappingTests.swift).
enum RedeemErrorMapping {
    static func message(from detail: String) -> String {
        let d = detail.lowercased()
        if d.contains("point") || d.contains("insufficient") {
            return "Not enough points for this reward."
        }
        if d.contains("sold") || d.contains("quantity") {
            return "This reward is sold out."
        }
        if d.contains("board") || d.contains("member") {
            return "Members-only reward — join the brand's board first."
        }
        return detail
    }
}
