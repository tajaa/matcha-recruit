import XCTest
@testable import TellUs

final class FriendModelDecodeTests: XCTestCase {
    func testFriendSummaryFromOldServerDecodes() throws {
        let data = #"{"account_id":"a1","display_name":"Jane","is_you":false}"#.data(using: .utf8)!
        let summary = try JSONDecoder().decode(FriendSummary.self, from: data)
        XCTAssertEqual(summary.display_name, "Jane")
        XCTAssertEqual(summary.level, 1)
        XCTAssertEqual(summary.status, .none)
    }

    func testNullDisplayNameUsesSomeone() throws {
        let data = #"{"account_id":"a1","display_name":null}"#.data(using: .utf8)!
        XCTAssertEqual(try JSONDecoder().decode(FriendSummary.self, from: data).display_name, "Someone")
    }

    func testProfileDistinguishesHiddenSectionsFromEmpty() throws {
        let data = #"{"account_id":"a1","display_name":"Jane","reviews":null,"followed_places":[],"boards":null}"#.data(using: .utf8)!
        let profile = try JSONDecoder().decode(FriendProfile.self, from: data)
        XCTAssertNil(profile.reviews)
        XCTAssertEqual(profile.followed_places?.count, 0)
        XCTAssertNil(profile.boards)
    }
}
