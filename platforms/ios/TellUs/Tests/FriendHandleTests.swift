import XCTest
@testable import TellUs

final class FriendHandleTests: XCTestCase {
    func testNormalizeIsIdempotent() {
        let once = FriendHandle.normalize(" @Finch_42 ")
        XCTAssertEqual(once, "finch_42")
        XCTAssertEqual(FriendHandle.normalize(once), once)
    }

    func testValidateBoundariesAndReservedPrefixes() {
        XCTAssertFalse(FriendHandle.validate("ab"))
        XCTAssertFalse(FriendHandle.validate(String(repeating: "a", count: 21)))
        XCTAssertFalse(FriendHandle.validate("member_a1b2"))
        XCTAssertFalse(FriendHandle.validate("tellus_team"))
        XCTAssertTrue(FriendHandle.validate("finch_42"))
    }
}
