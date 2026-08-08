import XCTest
@testable import TellUs

final class PlaceModelDecodeTests: XCTestCase {
    func testSearchResultDecodes() throws {
        let json = """
        {"slug":"joes-cafe","name":"Joe's Cafe","logo_url":null,"city":"Austin",
         "state":"TX","claimed":false,"intake_token":"tok123","review_count":4,
         "google_place_id":"ChIJabc"}
        """.data(using: .utf8)!
        let decoded = try JSONDecoder().decode(PlaceSearchResult.self, from: json)
        XCTAssertEqual(decoded.intake_token, "tok123")
        XCTAssertEqual(decoded.review_count, 4)
        XCTAssertEqual(decoded.id, "joes-cafe")
    }

    func testSearchResultClaimedNullToken() throws {
        let json = """
        {"slug":"acme","name":"Acme","logo_url":null,"city":null,"state":null,
         "claimed":true,"intake_token":null,"review_count":0,"google_place_id":null}
        """.data(using: .utf8)!
        let decoded = try JSONDecoder().decode(PlaceSearchResult.self, from: json)
        XCTAssertTrue(decoded.claimed)
        XCTAssertNil(decoded.intake_token)
    }

    func testSuggestionDecodesWithNullSecondary() throws {
        let json = """
        {"place_id":"ChIJx","name":"New Spot","secondary_text":null}
        """.data(using: .utf8)!
        let decoded = try JSONDecoder().decode(PlaceSuggestion.self, from: json)
        XCTAssertEqual(decoded.id, "ChIJx")
        XCTAssertNil(decoded.secondary_text)
    }

    func testCreateResponseDecodes() throws {
        let json = """
        {"slug":"new-spot","name":"New Spot","claimed":false,"intake_token":"tok9","existing":false}
        """.data(using: .utf8)!
        let decoded = try JSONDecoder().decode(PlaceCreateResponse.self, from: json)
        XCTAssertEqual(decoded.intake_token, "tok9")
        XCTAssertFalse(decoded.existing)
    }

    func testCreateRequestEncodingOmitsNilsAndHoneypot() throws {
        // Synthesized Encodable calls encodeIfPresent for Optional stored
        // properties, so nil keys (including the unset honeypot) are OMITTED
        // entirely rather than written as "null" — matches server expectations
        // (website must be either absent or an empty string, never populated).
        let request = PlaceCreateRequest(name: "X", google_place_id: "ChIJ1", session_token: "s1")
        let data = try JSONEncoder().encode(request)
        let json = String(data: data, encoding: .utf8)!
        XCTAssertFalse(json.contains("\"website\""))
        XCTAssertFalse(json.contains("\"city\""))
        XCTAssertFalse(json.contains("\"state\""))
        XCTAssertTrue(json.contains("\"google_place_id\":\"ChIJ1\""))
        XCTAssertTrue(json.contains("\"session_token\":\"s1\""))
    }
}
