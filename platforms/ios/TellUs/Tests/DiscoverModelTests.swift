import XCTest
@testable import TellUs

final class DiscoverModelTests: XCTestCase {
    private func makeEntry(
        source: DiscoverSource, slug: String? = nil, googlePlaceId: String? = nil,
        name: String = "X"
    ) -> DiscoverEntry {
        DiscoverEntry(
            source: source, name: name, slug: slug, google_place_id: googlePlaceId,
            logo_url: nil, city: nil, state: nil, address: nil, distance_km: nil,
            category_label: nil, rating: nil, review_count: 0, rating_count: 0,
            claimed: false, has_board: false, followed: false, messaging_enabled: false,
            intake_token: nil
        )
    }

    func testGoogleEntryIdentityFallsBackToPlaceId() {
        let entry = makeEntry(source: .google, googlePlaceId: "ChIJ_A", name: "Blue Bottle")
        XCTAssertEqual(entry.id, "ChIJ_A")
    }

    func testTellusEntryIdentityUsesSlug() {
        let entry = makeEntry(source: .tellus, slug: "blue-bottle", googlePlaceId: "ChIJ_A")
        XCTAssertEqual(entry.id, "blue-bottle")
    }

    func testDecodesGoogleEntryWithNullSlugAndNullDistance() throws {
        let json = """
        {"source":"google","name":"In-N-Out","slug":null,"google_place_id":"ChIJ_B",
         "logo_url":null,"city":null,"state":null,"address":"7009 Sunset Blvd",
         "distance_km":null,"category_label":null,"rating":4.5,"review_count":21217,
         "rating_count":21217,"claimed":false,"has_board":false,"followed":false,
         "messaging_enabled":false,"intake_token":null}
        """.data(using: .utf8)!
        let entry = try JSONDecoder().decode(DiscoverEntry.self, from: json)
        XCTAssertNil(entry.slug)
        XCTAssertNil(entry.distance_km)
        XCTAssertEqual(entry.id, "ChIJ_B")
    }

    func testDecodesTellusEntryWithAllFieldsPresent() throws {
        let json = """
        {"source":"tellus","name":"Sightglass Coffee","slug":"sightglass-coffee",
         "google_place_id":"ChIJ_C","logo_url":null,"city":"Los Angeles","state":"CA",
         "address":null,"distance_km":1.6,"category_label":null,"rating":4.0,
         "review_count":1,"rating_count":1,"claimed":true,"has_board":true,
         "followed":false,"messaging_enabled":false,"intake_token":null}
        """.data(using: .utf8)!
        let entry = try JSONDecoder().decode(DiscoverEntry.self, from: json)
        XCTAssertEqual(entry.slug, "sightglass-coffee")
        XCTAssertEqual(entry.distance_km, 1.6)
        XCTAssertTrue(entry.claimed)
        XCTAssertTrue(entry.has_board)
    }
}
