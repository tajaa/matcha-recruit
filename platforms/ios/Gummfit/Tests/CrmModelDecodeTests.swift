import XCTest
@testable import Gummfit

/// Pins CappeThreadDetail/CappeClient/CappeReview decode against real server
/// response shapes (server/app/cappe/models/engage.py).
final class CrmModelDecodeTests: XCTestCase {
    func testThreadDetailDecodesWithNestedMessages() throws {
        let json = """
        {
          "id": "thread-1", "site_id": "site-1", "client_email": "jane@example.com",
          "client_name": "Jane Doe", "subject": "Question", "status": "open",
          "booking_id": null, "order_id": null, "owner_unread": 0,
          "last_message_at": "2026-08-01T00:00:00Z", "created_at": "2026-08-01T00:00:00Z",
          "last_snippet": "Thanks!", "access_token": "tok-1",
          "messages": [
            {"id": "msg-1", "thread_id": "thread-1", "sender": "client", "body": "Hi", "created_at": "2026-08-01T00:00:00Z"},
            {"id": "msg-2", "thread_id": "thread-1", "sender": "owner", "body": "Hello!", "created_at": "2026-08-01T00:01:00Z"}
          ]
        }
        """
        let detail = try JSONDecoder().decode(CappeThreadDetail.self, from: Data(json.utf8))
        XCTAssertEqual(detail.messages.count, 2)
        XCTAssertEqual(detail.messages[1].sender, "owner")
        XCTAssertEqual(detail.owner_unread, 0)
    }

    func testClientDecodesUsingEmailAsId() throws {
        let json = """
        {"email": "jane@example.com", "name": "Jane Doe", "phone": null, "orders_count": 3,
         "bookings_count": 1, "is_subscriber": true, "has_thread": true, "is_imported": false,
         "total_spent_cents": 4500, "last_activity": "2026-08-01T00:00:00Z",
         "location_id": null, "location_name": null}
        """
        let client = try JSONDecoder().decode(CappeClient.self, from: Data(json.utf8))
        XCTAssertEqual(client.id, "jane@example.com")
        XCTAssertEqual(client.orders_count, 3)
    }

    func testReviewDecodesWithNullableRating() throws {
        let json = """
        {"id": "rev-1", "site_id": "site-1", "author_name": "Anon", "rating": null,
         "body": "Great!", "status": "pending", "created_at": "2026-08-01T00:00:00Z"}
        """
        let review = try JSONDecoder().decode(CappeReview.self, from: Data(json.utf8))
        XCTAssertNil(review.rating)
        XCTAssertEqual(review.status, "pending")
    }
}
