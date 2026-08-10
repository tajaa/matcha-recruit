import XCTest
@testable import TellUs

final class ParityModelDecodeTests: XCTestCase {
    func testDmThreadDecodes() throws {
        let json = """
        {"id":"t1","report_id":"r1","counterparty_name":"Jane","report_title":null,
         "report_number":"TU-1","review_state":"held","publish_at":null,
         "blocked":false,"unread_count":2,"last_message_at":"2026-01-01T00:00:00Z",
         "created_at":"2026-01-01T00:00:00Z"}
        """
        let thread = try JSONDecoder().decode(DmThread.self, from: Data(json.utf8))
        XCTAssertEqual(thread.unread_count, 2)
        XCTAssertFalse(thread.blocked)
        XCTAssertNil(thread.report_title)
    }

    func testDmMessageIsMine() throws {
        let json = """
        {"id":"m1","thread_id":"t1","sender_role":"consumer","body":"hi",
         "created_at":"2026-01-01T00:00:00Z","is_mine":true}
        """
        let message = try JSONDecoder().decode(DmMessage.self, from: Data(json.utf8))
        XCTAssertTrue(message.is_mine)
        XCTAssertEqual(message.sender_role, .consumer)
    }

    func testBrandDecodes() throws {
        let json = """
        {"id":"b1","owner_account_id":"a1","name":"Acme","logo_url":null,
         "reward_mode":"manual","created_at":"2026-01-01T00:00:00Z","messaging_enabled":true}
        """
        let brand = try JSONDecoder().decode(Brand.self, from: Data(json.utf8))
        XCTAssertEqual(brand.reward_mode, .manual)
        XCTAssertTrue(brand.messaging_enabled)
    }

    func testStoreDecodes() throws {
        let json = """
        {"id":"s1","brand_id":"b1","name":"Main St","address":null,"city":null,
         "state":null,"zipcode":null,"lat":37.5,"lng":-122.1,
         "created_at":"2026-01-01T00:00:00Z"}
        """
        let store = try JSONDecoder().decode(Store.self, from: Data(json.utf8))
        XCTAssertEqual(store.lat, 37.5)
        XCTAssertNil(store.address)
    }

    func testFeedbackLinkDecodes() throws {
        let json = """
        {"id":"l1","brand_id":"b1","store_id":null,"token":"abc123","label":null,
         "is_active":true,"use_count":5,"max_uses":null,"expires_at":null,
         "revoked_at":null,"created_at":"2026-01-01T00:00:00Z","store_name":null}
        """
        let link = try JSONDecoder().decode(FeedbackLink.self, from: Data(json.utf8))
        XCTAssertEqual(link.use_count, 5)
        XCTAssertNil(link.max_uses)
        XCTAssertNil(link.revoked_at)
    }

    func testBillingStatusDecodes() throws {
        let json = """
        {"plan_status":"active","location_count":3,"store_count":2,
         "price_per_location_cents":500,"monthly_total_cents":1500,"price_available":true}
        """
        let status = try JSONDecoder().decode(BillingStatus.self, from: Data(json.utf8))
        XCTAssertEqual(status.plan_status, .active)
        XCTAssertEqual(status.monthly_total_cents, 1500)
    }

    func testLeaderboardEntryIdIsAccount() throws {
        let json = """
        {"rank":1,"account_id":"a1","display_name":"Jane","lifetime_points":500,
         "level":3,"is_you":true}
        """
        let entry = try JSONDecoder().decode(LeaderboardEntry.self, from: Data(json.utf8))
        XCTAssertEqual(entry.id, "a1")
        XCTAssertTrue(entry.is_you)
    }

    func testBrandTeamMemberDecodes() throws {
        let json = """
        {"id":"tm1","account_display_name":"Jane","email":"jane@example.com",
         "role":"moderator","created_at":"2026-01-01T00:00:00Z","can_manage_inbox":true}
        """
        let member = try JSONDecoder().decode(BrandTeamMember.self, from: Data(json.utf8))
        XCTAssertEqual(member.role, "moderator")
        XCTAssertTrue(member.can_manage_inbox)
    }

    func testListingCreateOmitsNilKeys() throws {
        let create = ListingCreate(
            title: "Free coffee", description: nil, image_url: nil, points_cost: 100,
            quantity_total: nil, redemption_type: "code", terms: nil, city: nil, state: nil,
            active_from: nil, active_to: nil, is_active: true, expiry_days: 30, visibility: "public"
        )
        let data = try JSONEncoder().encode(create)
        let json = String(data: data, encoding: .utf8)!
        XCTAssertFalse(json.contains("\"description\""))
        XCTAssertFalse(json.contains("\"terms\""))
        XCTAssertTrue(json.contains("\"points_cost\":100"))
    }

    func testBoardPostUpdateEncodes() throws {
        let update = BoardPostUpdate(title: "New title", body: nil, is_pinned: true)
        let data = try JSONEncoder().encode(update)
        let json = String(data: data, encoding: .utf8)!
        XCTAssertTrue(json.contains("\"title\":\"New title\""))
        XCTAssertTrue(json.contains("\"is_pinned\":true"))
        XCTAssertFalse(json.contains("\"body\""))
    }
}
