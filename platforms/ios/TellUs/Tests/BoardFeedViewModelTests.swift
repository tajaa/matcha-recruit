import XCTest
@testable import TellUs

@MainActor
final class BoardFeedViewModelTests: XCTestCase {
    func testMarkPendingMembershipShowsPendingLockState() {
        let vm = BoardFeedViewModel(slug: "qa-coffee-co")
        vm.error = "stale error"

        vm.markPendingMembership()

        XCTAssertNil(vm.page)
        XCTAssertTrue(vm.notAMember)
        XCTAssertEqual(vm.membershipStatus, .pending)
        XCTAssertFalse(vm.boardPaused)
        XCTAssertNil(vm.error)
    }

    func testMarkPausedBoardShowsPausedState() {
        let vm = BoardFeedViewModel(slug: "qa-coffee-co")
        vm.error = "stale error"

        vm.markPausedBoard()

        XCTAssertNil(vm.page)
        XCTAssertTrue(vm.notAMember)
        XCTAssertTrue(vm.boardPaused)
        XCTAssertNil(vm.membershipStatus)
        XCTAssertNil(vm.error)
    }
}
