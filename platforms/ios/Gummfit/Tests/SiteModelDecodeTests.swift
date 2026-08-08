import XCTest
@testable import Gummfit

/// Pins CappeSite/CappeReadiness/CappeDirectoryListing decode against real
/// server response shapes (server/app/cappe/models/sites.py, types.ts:51-134).
final class SiteModelDecodeTests: XCTestCase {
    func testSiteDecodesWithNullableFields() throws {
        let json = """
        {
          "id": "site-1", "account_id": "acct-1", "name": "Cara's Bakery",
          "slug": "caras-bakery", "subdomain": "caras-bakery", "custom_domain": null,
          "source_type": "blank", "status": "draft", "is_multi_location": false,
          "published_at": null, "created_at": "2026-08-01T00:00:00Z",
          "updated_at": "2026-08-01T00:00:00Z", "page_count": 1
        }
        """
        let site = try JSONDecoder().decode(CappeSite.self, from: Data(json.utf8))
        XCTAssertEqual(site.status, .draft)
        XCTAssertNil(site.custom_domain)
        XCTAssertEqual(site.publicURLString, "https://caras-bakery.gummfit.com")
    }

    func testCustomDomainWinsOverSubdomainForPublicURL() throws {
        let json = """
        {
          "id": "site-1", "account_id": "acct-1", "name": "Cara's Bakery",
          "slug": "caras-bakery", "subdomain": "caras-bakery", "custom_domain": "carasbakery.com",
          "source_type": "blank", "status": "published", "is_multi_location": false,
          "published_at": "2026-08-01T00:00:00Z", "created_at": "2026-08-01T00:00:00Z",
          "updated_at": "2026-08-01T00:00:00Z", "page_count": 3
        }
        """
        let site = try JSONDecoder().decode(CappeSite.self, from: Data(json.utf8))
        XCTAssertEqual(site.publicURLString, "https://carasbakery.com")
    }

    func testUnknownSiteStatusFallsBackNotThrows() throws {
        let decoded = try JSONDecoder().decode(SiteStatus.self, from: Data("\"suspended\"".utf8))
        XCTAssertEqual(decoded, .unknown)
    }

    func testReadinessDecodes() throws {
        let json = """
        {"ready": false, "items": [
          {"key": "intro", "label": "Add an intro", "hint": "Say what you do", "done": false, "required": true, "action": "pages"},
          {"key": "product", "label": "Add a product", "hint": "List something for sale", "done": true, "required": false, "action": "shop"}
        ]}
        """
        let readiness = try JSONDecoder().decode(CappeReadiness.self, from: Data(json.utf8))
        XCTAssertFalse(readiness.ready)
        XCTAssertEqual(readiness.items.count, 2)
        XCTAssertEqual(readiness.items[0].action, "pages")
        XCTAssertTrue(readiness.items[1].done)
    }

    func testDirectoryListingDecodesWithCategoryOptions() throws {
        let json = """
        {"listed": true, "category": "bakery", "category_label": "Bakery", "tags": ["vegan"],
         "blurb": "Fresh daily", "confirmed_at": null, "visible": true, "blocked": false,
         "categories": [{"slug": "bakery", "label": "Bakery"}, {"slug": "cafe", "label": "Cafe"}]}
        """
        let listing = try JSONDecoder().decode(CappeDirectoryListing.self, from: Data(json.utf8))
        XCTAssertTrue(listing.listed)
        XCTAssertEqual(listing.categories.count, 2)
        XCTAssertEqual(listing.categories[0].slug, "bakery")
    }
}

/// `CappeDirectoryListingUpdate` must round-trip PATCH semantics: an unset
/// field is genuinely ABSENT from the JSON, not sent as `null` — the server
/// keys off `model_fields_set`, not null-checks (models/sites.py:145-151).
final class DirectoryUpdateEncodeTests: XCTestCase {
    func testOnlySetFieldsAreEncoded() throws {
        let update = CappeDirectoryListingUpdate(listed: true)
        let data = try JSONEncoder().encode(update)
        let json = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        XCTAssertEqual(json["listed"] as? Bool, true)
        XCTAssertNil(json["category"])
        XCTAssertNil(json["tags"])
        XCTAssertNil(json["blurb"])
        XCTAssertEqual(json.count, 1)
    }
}
