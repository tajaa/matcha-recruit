import XCTest
@testable import TellUs

final class BoardTabLoadStateTests: XCTestCase {
    func testBeginMovesIdleToLoading() {
        var state = TabLoadState()
        XCTAssertEqual(state.phase(.posts), .idle)
        XCTAssertTrue(state.begin(.posts))
        XCTAssertEqual(state.phase(.posts), .loading)
    }

    func testBeginSkipsWhileAlreadyLoading() {
        var state = TabLoadState()
        XCTAssertTrue(state.begin(.posts))
        XCTAssertFalse(state.begin(.posts))
        XCTAssertEqual(state.phase(.posts), .loading)
    }

    func testBeginSkipsWhenLoadedUnlessForced() {
        var state = TabLoadState()
        _ = state.begin(.posts)
        state.succeed(.posts)
        XCTAssertFalse(state.begin(.posts))
        XCTAssertEqual(state.phase(.posts), .loaded)
    }

    func testForcedBeginReloadsLoadedTab() {
        var state = TabLoadState()
        _ = state.begin(.posts)
        state.succeed(.posts)
        XCTAssertTrue(state.begin(.posts, force: true))
        XCTAssertEqual(state.phase(.posts), .loading)
    }

    func testCancelReturnsToIdleSoNextBeginRetries() {
        var state = TabLoadState()
        _ = state.begin(.posts)
        state.cancel(.posts)
        XCTAssertEqual(state.phase(.posts), .idle)
        XCTAssertTrue(state.begin(.posts))
    }

    func testFailedTabRetriesOnNextBegin() {
        var state = TabLoadState()
        _ = state.begin(.posts)
        state.fail(.posts)
        XCTAssertEqual(state.phase(.posts), .failed)
        XCTAssertTrue(state.begin(.posts))
    }

    func testTabsTrackIndependently() {
        var state = TabLoadState()
        _ = state.begin(.posts)
        XCTAssertEqual(state.phase(.posts), .loading)
        XCTAssertEqual(state.phase(.members), .idle)
    }

    func testIsAnyLoadingReflectsAnyTabInFlight() {
        var state = TabLoadState()
        XCTAssertFalse(state.isAnyLoading)
        _ = state.begin(.team)
        XCTAssertTrue(state.isAnyLoading)
        state.succeed(.team)
        XCTAssertFalse(state.isAnyLoading)
    }

    func testInvalidateResetsTabToIdle() {
        var state = TabLoadState()
        _ = state.begin(.posts)
        state.succeed(.posts)
        state.invalidate(.posts)
        XCTAssertEqual(state.phase(.posts), .idle)
        XCTAssertTrue(state.begin(.posts))
    }

    func testHasLoadedOnlyTrueWhenLoaded() {
        var state = TabLoadState()
        XCTAssertFalse(state.hasLoaded(.posts))
        _ = state.begin(.posts)
        XCTAssertFalse(state.hasLoaded(.posts))
        state.fail(.posts)
        XCTAssertFalse(state.hasLoaded(.posts))
        state.succeed(.posts)
        XCTAssertTrue(state.hasLoaded(.posts))
    }
}
