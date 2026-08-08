import XCTest
@testable import TellUs

final class RedeemErrorMappingTests: XCTestCase {
    func testInsufficient() {
        XCTAssertEqual(
            RedeemErrorMapping.message(from: "Insufficient points"),
            "Not enough points for this reward."
        )
    }

    func testSoldOut() {
        XCTAssertEqual(
            RedeemErrorMapping.message(from: "Reward sold out"),
            "This reward is sold out."
        )
    }

    func testBoardOnly() {
        XCTAssertEqual(
            RedeemErrorMapping.message(from: "Board members only"),
            "Members-only reward — join the brand's board first."
        )
    }

    func testPassthrough() {
        XCTAssertEqual(
            RedeemErrorMapping.message(from: "Redemption window closed"),
            "Redemption window closed"
        )
    }
}
