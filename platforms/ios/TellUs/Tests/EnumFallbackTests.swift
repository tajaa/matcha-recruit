import XCTest
@testable import TellUs

final class EnumFallbackTests: XCTestCase {
    func testUnknownRedemptionStatus() throws {
        let data = "\"gifted\"".data(using: .utf8)!
        let decoded = try JSONDecoder().decode(RedemptionStatus.self, from: data)
        XCTAssertEqual(decoded, .unknown)
    }

    func testKnownRoundTrip() throws {
        for status: RedemptionStatus in [.pending, .issued, .redeemed, .expired, .cancelled] {
            let data = "\"\(status.rawValue)\"".data(using: .utf8)!
            let decoded = try JSONDecoder().decode(RedemptionStatus.self, from: data)
            XCTAssertEqual(decoded, status)
        }
    }

    func testUnknownInsideArray() throws {
        struct Wrapper: Codable { let status: RedemptionStatus }
        let json = """
        [{"status":"pending"},{"status":"gifted"},{"status":"redeemed"}]
        """.data(using: .utf8)!
        let decoded = try JSONDecoder().decode([Wrapper].self, from: json)
        XCTAssertEqual(decoded.map(\.status), [.pending, .unknown, .redeemed])
    }

    func testUnknownBoardPostKind() throws {
        let data = "\"raffle\"".data(using: .utf8)!
        let decoded = try JSONDecoder().decode(BoardPostKind.self, from: data)
        XCTAssertEqual(decoded, .unknown)
    }

    func testUnknownFriendEnumsInsideArrays() throws {
        let json = #"["friends","future_status"]"#.data(using: .utf8)!
        let decoded = try JSONDecoder().decode([FriendshipStatus].self, from: json)
        XCTAssertEqual(decoded, [.friends, .unknown])
        let visibility = try JSONDecoder().decode(ProfileVisibility.self, from: #""future_visibility""#.data(using: .utf8)!)
        XCTAssertEqual(visibility, .unknown)
    }
}
