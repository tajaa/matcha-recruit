import XCTest
@testable import TellUs

final class FriendsTabLoadStateTests: XCTestCase {
    private enum Tab: Hashable { case friends, requests }

    func testGenericTracksIndependentKeys() {
        var state = SectionLoadState<Tab>()
        XCTAssertTrue(state.begin(.friends))
        XCTAssertEqual(state.phase(.requests), .idle)
        state.succeed(.friends)
        XCTAssertTrue(state.hasLoaded(.friends))
    }
}
