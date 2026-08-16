import XCTest
@testable import TellUs

final class CampaignModelTests: XCTestCase {
    func testCreateRequestEncodesWireFieldsAndOmitsNilOptionals() throws {
        let body = PromoCampaignCreate(
            title: "Free coffee",
            reward_text: "One free coffee",
            max_claims: 50,
            card_expiry_days: 30
        )

        let json = try XCTUnwrap(String(data: JSONEncoder().encode(body), encoding: .utf8))
        XCTAssertTrue(json.contains("\"title\":\"Free coffee\""))
        XCTAssertTrue(json.contains("\"reward_text\":\"One free coffee\""))
        XCTAssertTrue(json.contains("\"max_claims\":50"))
        XCTAssertTrue(json.contains("\"card_expiry_days\":30"))
        XCTAssertFalse(json.contains("description"))
        XCTAssertFalse(json.contains("starts_at"))
        XCTAssertFalse(json.contains("ends_at"))
    }

    func testCreateRequestEncodesEndDateWithoutChangingIt() throws {
        let body = PromoCampaignCreate(
            title: "Event offer",
            reward_text: "10% off",
            max_claims: 100,
            card_expiry_days: 7,
            ends_at: "2026-09-01T12:30:00Z"
        )

        let json = try XCTUnwrap(String(data: JSONEncoder().encode(body), encoding: .utf8))
        XCTAssertTrue(json.contains("\"ends_at\":\"2026-09-01T12:30:00Z\""))
    }

    func testLocationCampaignEncodesStoreAndRadius() throws {
        let body = PromoCampaignCreate(
            title: "Nearby", reward_text: "Free coffee", max_claims: 25,
            campaign_type: "location", store_id: "store-1", radius_miles: 7.5
        )
        let json = try XCTUnwrap(String(data: JSONEncoder().encode(body), encoding: .utf8))
        XCTAssertTrue(json.contains("\"campaign_type\":\"location\""))
        XCTAssertTrue(json.contains("\"store_id\":\"store-1\""))
        XCTAssertTrue(json.contains("\"radius_miles\":7.5"))
    }

    func testDraftTrimsTextAndBuildsCreateRequest() throws {
        var draft = PromoCampaignDraft()
        draft.title = "  Free coffee  "
        draft.rewardText = "  One coffee  "
        draft.description = "  Today only  "
        draft.maxClaims = " 50 "

        let body = try draft.validated(now: date("2026-08-12T00:00:00Z"))
        XCTAssertEqual(body.title, "Free coffee")
        XCTAssertEqual(body.reward_text, "One coffee")
        XCTAssertEqual(body.description, "Today only")
        XCTAssertEqual(body.max_claims, 50)
    }

    func testDraftRejectsMissingRequiredText() {
        var draft = PromoCampaignDraft()
        draft.rewardText = "A reward"
        XCTAssertThrowsError(try draft.validated()) { error in
            XCTAssertEqual(error as? PromoCampaignValidationError, .titleRequired)
        }

        draft.title = "A title"
        draft.rewardText = ""
        XCTAssertThrowsError(try draft.validated()) { error in
            XCTAssertEqual(error as? PromoCampaignValidationError, .rewardRequired)
        }
    }

    func testDraftRejectsTextOverLimits() {
        var draft = PromoCampaignDraft()
        draft.title = String(repeating: "t", count: 121)
        draft.rewardText = "Reward"
        XCTAssertThrowsError(try draft.validated()) { error in
            XCTAssertEqual(error as? PromoCampaignValidationError, .titleTooLong)
        }

        draft.title = "Title"
        draft.rewardText = String(repeating: "r", count: 201)
        XCTAssertThrowsError(try draft.validated()) { error in
            XCTAssertEqual(error as? PromoCampaignValidationError, .rewardTooLong)
        }

        draft.rewardText = "Reward"
        draft.description = String(repeating: "d", count: 2_001)
        XCTAssertThrowsError(try draft.validated()) { error in
            XCTAssertEqual(error as? PromoCampaignValidationError, .descriptionTooLong)
        }
    }

    func testDraftRejectsClaimLimitOutsideRange() {
        var draft = validDraft()
        for value in ["0", "10001", "1.5", ""] {
            draft.maxClaims = value
            XCTAssertThrowsError(try draft.validated()) { error in
                XCTAssertEqual(error as? PromoCampaignValidationError, .invalidClaimLimit)
            }
        }
    }

    func testDraftAcceptsClaimLimitBoundaries() throws {
        var draft = validDraft()
        for value in ["1", "10000"] {
            draft.maxClaims = value
            XCTAssertEqual(try draft.validated().max_claims, Int(value))
        }
    }

    func testDraftRejectsExpiryDaysOutsideRange() {
        var draft = validDraft()
        for value in ["0", "366", "1.5", ""] {
            draft.expiryDays = value
            XCTAssertThrowsError(try draft.validated()) { error in
                XCTAssertEqual(error as? PromoCampaignValidationError, .invalidExpiryDays)
            }
        }
    }

    func testDraftAcceptsExpiryDaysBoundaries() throws {
        var draft = validDraft()
        for value in ["1", "365"] {
            draft.expiryDays = value
            XCTAssertEqual(try draft.validated().card_expiry_days, Int(value))
        }
    }

    func testDraftRejectsEndDateInPast() {
        var draft = validDraft()
        draft.hasEndDate = true
        draft.endDate = date("2026-08-11T00:00:00Z")

        XCTAssertThrowsError(try draft.validated(now: date("2026-08-12T00:00:00Z"))) { error in
            XCTAssertEqual(error as? PromoCampaignValidationError, .endDateInPast)
        }
    }

    func testCampaignResponseDecodes() throws {
        let json = """
        {"id":"c1","title":"Free coffee","description":null,
         "reward_text":"One coffee","claim_token":"claim-token",
         "claim_url":"/tellus/p/claim-token","max_claims":50,"claim_count":0,
         "status":"active","card_expiry_days":30,"starts_at":null,"ends_at":null,
         "flyer_image_url":null,"has_design":false,"cancelled_at":null,
         "created_at":"2026-08-12T00:00:00Z","stats":null}
        """

        let campaign = try JSONDecoder().decode(PromoCampaign.self, from: Data(json.utf8))
        XCTAssertEqual(campaign.id, "c1")
        XCTAssertEqual(campaign.claim_url, "/tellus/p/claim-token")
        XCTAssertEqual(campaign.status, "active")
        XCTAssertNil(campaign.stats)
    }

    private func validDraft() -> PromoCampaignDraft {
        var draft = PromoCampaignDraft()
        draft.title = "Campaign"
        draft.rewardText = "Reward"
        return draft
    }

    private func date(_ value: String) -> Date {
        ISO8601DateFormatter().date(from: value)!
    }
}
