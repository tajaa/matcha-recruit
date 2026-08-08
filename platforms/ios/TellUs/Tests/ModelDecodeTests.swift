import XCTest
@testable import TellUs

final class ModelDecodeTests: XCTestCase {
    func testTokenResponseDecodes() throws {
        let json = """
        {
          "access_token": "a", "refresh_token": "r", "expires_in": 86400,
          "account": {
            "id": "acc1", "email": "test@example.com", "display_name": null,
            "account_type": "consumer", "status": "active", "city": null, "state": null,
            "leaderboard_opt_in": true, "brand_id": null, "plan_status": null,
            "location_count": null, "brand_slug": null, "is_admin": false
          }
        }
        """.data(using: .utf8)!
        let decoded = try JSONDecoder().decode(TokenResponse.self, from: json)
        XCTAssertEqual(decoded.access_token, "a")
        XCTAssertEqual(decoded.account.account_type, .consumer)
    }

    func testSignupResponseWithoutTokens() throws {
        let json = """
        {"verification_required": true, "email": "test@example.com"}
        """.data(using: .utf8)!
        let decoded = try JSONDecoder().decode(SignupResponse.self, from: json)
        XCTAssertTrue(decoded.verification_required)
        XCTAssertNil(decoded.access_token)
        XCTAssertNil(decoded.account)
    }

    func testPointsBalanceProgress() throws {
        let balance = PointsBalance(
            account_id: "a", points_balance: 10, lifetime_points: 150, level: 3,
            current_streak: 0, longest_streak: 0, last_activity_date: nil,
            points_to_next_level: 150, level_floor: 100, level_ceiling: 300
        )
        XCTAssertEqual(balance.levelProgress, 0.25, accuracy: 0.0001)
    }

    func testBoardPostDealEmbedsListing() throws {
        let json = """
        {
          "id": "p1", "kind": "deal", "title": "Deal!", "body": null,
          "listing": {
            "id": "l1", "brand_id": "b1", "brand_name": "Acme", "city": null, "state": null,
            "title": "Free coffee", "description": null, "image_url": null, "points_cost": 100,
            "quantity_total": 10, "quantity_claimed": 0, "quantity_remaining": 10,
            "redemption_type": "code", "terms": null, "active_from": null, "active_to": null,
            "is_active": true, "created_at": "2026-01-01T00:00:00Z", "expiry_days": 30,
            "visibility": "board"
          },
          "event_starts_at": null, "event_ends_at": null, "is_pinned": false,
          "moderation_status": "visible", "approved_reply_count": 0, "held_reply_count": 2,
          "created_at": "2026-01-01T00:00:00Z"
        }
        """.data(using: .utf8)!
        let decoded = try JSONDecoder().decode(BoardPost.self, from: json)
        XCTAssertEqual(decoded.kind, .deal)
        XCTAssertEqual(decoded.listing?.title, "Free coffee")
    }

    /// Fixture matches server/app/tellus/routes/board.py:632-639's dict literal
    /// for GET /board/manage/replies (no response_model on that endpoint).
    func testBoardManageReplyRowDecodes() throws {
        let json = """
        {
          "id": "r1", "post_id": "p1", "post_title": "Welcome!",
          "author_name": "Tell-Us member", "body": "Great news",
          "status": "held", "created_at": "2026-01-01T00:00:00Z"
        }
        """.data(using: .utf8)!
        let decoded = try JSONDecoder().decode(BoardManageReplyRow.self, from: json)
        XCTAssertEqual(decoded.status, .held)
        XCTAssertEqual(decoded.author_name, "Tell-Us member")
    }

    func testReportFullShape() throws {
        let json = """
        {
          "id": "rep1", "brand_id": "b1", "store_id": null, "store_name": null,
          "report_number": "R-001", "category": "service", "sentiment": "positive",
          "title": "Great service", "description": "Loved it", "occurred_at": null,
          "reporter_contact": null, "usefulness_score": 40, "status": "new",
          "ai_summary": null, "moderation_status": "visible", "reward_status": "pending",
          "points_awarded": 0, "created_at": "2026-01-01T00:00:00Z", "media": [],
          "rating": 5, "review_state": "held", "publish_at": "2026-01-03T00:00:00Z",
          "hearted_at": null, "brand_public_reply": null, "brand_public_reply_at": null,
          "is_identified": true, "has_dm_thread": false, "answers": []
        }
        """.data(using: .utf8)!
        let decoded = try JSONDecoder().decode(Report.self, from: json)
        XCTAssertEqual(decoded.category, .service)
        XCTAssertEqual(decoded.reward_status, .pending)
        XCTAssertEqual(decoded.review_state, .held)
    }

    func testMyReviewIsEditable() throws {
        func review(state: String) throws -> MyReview {
            let json = """
            {
              "id": "rv1", "brand_name": "Acme", "brand_slug": "acme", "store_name": null,
              "rating": 5, "title": null, "description": null, "review_state": "\(state)",
              "publish_at": "2026-01-03T00:00:00Z", "created_at": "2026-01-01T00:00:00Z",
              "points_awarded": 10, "hearted": false, "brand_public_reply": null,
              "brand_public_reply_at": null, "dm_thread_id": null, "media": [], "answers": []
            }
            """.data(using: .utf8)!
            return try JSONDecoder().decode(MyReview.self, from: json)
        }
        XCTAssertTrue(try review(state: "held").isEditable)
        XCTAssertFalse(try review(state: "published").isEditable)
        XCTAssertFalse(try review(state: "withdrawn").isEditable)
    }
}
