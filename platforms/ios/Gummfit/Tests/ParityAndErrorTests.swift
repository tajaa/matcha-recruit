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
    func testPublicCreatorDirectoryDecodesSearchCard() throws {
        let data = Data(#"{"creators":[{"handle":"alex","display_name":"Alex","avatar_url":null,"cover_url":null,"bio":"fit","location":"LA","niches":["fitness"],"reach_verified":true,"max_followers":1000,"min_rate_cents":5000,"platforms":["instagram"]}],"total":1}"#.utf8)
        let page = try JSONDecoder().decode(PublicCreatorPage.self, from: data)
        XCTAssertEqual(page.creators.first?.handle, "alex")
        XCTAssertEqual(page.creators.first?.min_rate_cents, 5000)
    }
    func testJSONValuePreservesNestedPayload() throws {
        let value = try JSONDecoder().decode(JSONValue.self, from: Data(#"{"ok":true,"count":2}"#.utf8))
        XCTAssertEqual(value, .object(["ok": .bool(true), "count": .number(2)]))
    }
}
