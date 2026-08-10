import XCTest
@testable import Gummfit

final class ParityAndErrorTests: XCTestCase {
    func testCreatorUpdateRoundTripsJSONKeys() throws {
        let value = CreatorProfileUpdate(display_name: "A", avatar_url: nil, cover_url: nil, bio: "B", location: nil, niches: ["fitness"], languages: ["en"], open_to_offers: true)
        let data = try JSONEncoder().encode(value)
        let object = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        XCTAssertEqual(object["display_name"] as? String, "A")
        XCTAssertEqual(object["open_to_offers"] as? Bool, true)
    }
    func testStructuredErrorsKeepActionableMessages() {
        XCTAssertEqual(APIError.publishBlocked(message: "Complete setup", missing: ["shop"]).localizedDescription, "Complete setup")
        XCTAssertEqual(APIError.conflict(code: "payouts_not_ready", message: "Connect payouts").localizedDescription, "Connect payouts")
    }
}
