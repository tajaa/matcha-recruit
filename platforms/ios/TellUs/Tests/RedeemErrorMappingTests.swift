import XCTest
@testable import TellUs

@MainActor
final class RedeemErrorMappingTests: XCTestCase {
    func testInsufficient() {
        XCTAssertEqual(
            MarketplaceViewModel.redeemMessage(from: "Insufficient points"),
            "Not enough points for this reward."
        )
    }

    func testSoldOut() {
        XCTAssertEqual(
            MarketplaceViewModel.redeemMessage(from: "Reward sold out"),
            "This reward is sold out."
        )
    }

    func testBoardOnly() {
        XCTAssertEqual(
            MarketplaceViewModel.redeemMessage(from: "Board members only"),
            "Members-only reward — join the brand's board first."
        )
    }

    func testPassthrough() {
        XCTAssertEqual(
            MarketplaceViewModel.redeemMessage(from: "Redemption window closed"),
            "Redemption window closed"
        )
    }
}
