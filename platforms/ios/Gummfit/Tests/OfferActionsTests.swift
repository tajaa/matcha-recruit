import XCTest
@testable import Gummfit

final class OfferActionsTests: XCTestCase {
    func testCreatorCanAcceptOrDeclineBeforeAcceptance() {
        XCTAssertEqual(OfferActionPolicy.actions(side: "creator", status: "sent"), ["accept", "decline"])
    }
    func testBrandCanWithdrawBeforeAcceptance() {
        XCTAssertEqual(OfferActionPolicy.actions(side: "brand", status: "negotiating"), ["withdraw"])
    }
    func testTerminalOffersHaveNoActions() {
        XCTAssertTrue(OfferActionPolicy.actions(side: "creator", status: "completed").isEmpty)
    }
}
