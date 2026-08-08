import XCTest
@testable import TellUs

/// Pins the like fields' wire contract against server/app/tellus/models/tellus.py.
/// The omitted-field cases are the load-bearing ones: like_count/liked_by_me are
/// declared Optional precisely so an app build shipping ahead of the server
/// doesn't fail to decode an entire feed on a missing key.
final class LikeModelDecodeTests: XCTestCase {
    func testLikeStateDecodes() throws {
        let json = #"{"like_count":3,"liked_by_me":true}"#
        let state = try JSONDecoder().decode(LikeState.self, from: Data(json.utf8))
        XCTAssertEqual(state.like_count, 3)
        XCTAssertTrue(state.liked_by_me)
    }

    func testLikeTargetRawValuesMatchServerLiterals() {
        // Must match LikeTargetType in server/app/tellus/routes/likes.py — a
        // mismatch here is a 422 from FastAPI's path Literal validation.
        XCTAssertEqual(LikeTarget.boardPost.rawValue, "board_post")
        XCTAssertEqual(LikeTarget.boardReply.rawValue, "board_reply")
        XCTAssertEqual(LikeTarget.report.rawValue, "report")
        XCTAssertEqual(LikeTarget.listing.rawValue, "listing")
    }

    func testBoardPostDecodesWithLikes() throws {
        let json = """
        {"id":"p1","kind":"update","title":"Hello","body":null,"listing":null,
         "event_starts_at":null,"event_ends_at":null,"is_pinned":false,
         "moderation_status":"visible","approved_reply_count":2,"held_reply_count":null,
         "created_at":"2026-01-01T00:00:00Z","like_count":7,"liked_by_me":true}
        """
        let post = try JSONDecoder().decode(BoardPost.self, from: Data(json.utf8))
        XCTAssertEqual(post.likeCount, 7)
        XCTAssertTrue(post.likedByMe)
    }

    func testBoardPostDecodesWithLikeFieldsOmitted() throws {
        let json = """
        {"id":"p1","kind":"update","title":"Hello","body":null,"listing":null,
         "event_starts_at":null,"event_ends_at":null,"is_pinned":false,
         "moderation_status":"visible","approved_reply_count":0,"held_reply_count":null,
         "created_at":"2026-01-01T00:00:00Z"}
        """
        let post = try JSONDecoder().decode(BoardPost.self, from: Data(json.utf8))
        XCTAssertEqual(post.likeCount, 0)
        XCTAssertFalse(post.likedByMe)
    }

    func testBoardReplyDecodesWithLikeFieldsOmitted() throws {
        let json = """
        {"id":"r1","post_id":"p1","author_name":"Jane","is_mine":false,
         "status":"approved","body":"nice","created_at":"2026-01-01T00:00:00Z"}
        """
        let reply = try JSONDecoder().decode(BoardReply.self, from: Data(json.utf8))
        XCTAssertEqual(reply.likeCount, 0)
        XCTAssertFalse(reply.likedByMe)
    }

    func testListingDecodesWithLikes() throws {
        let json = """
        {"id":"l1","brand_id":"b1","brand_name":"Acme","city":null,"state":null,
         "title":"Free coffee","description":null,"image_url":null,"points_cost":100,
         "quantity_total":null,"quantity_claimed":0,"quantity_remaining":null,
         "redemption_type":"code","terms":null,"active_from":null,"active_to":null,
         "is_active":true,"created_at":"2026-01-01T00:00:00Z","expiry_days":30,
         "visibility":"public","like_count":4,"liked_by_me":false}
        """
        let listing = try JSONDecoder().decode(Listing.self, from: Data(json.utf8))
        XCTAssertEqual(listing.likeCount, 4)
        XCTAssertFalse(listing.likedByMe)
    }

    func testMyReviewDecodesWithLikeFieldsOmitted() throws {
        let json = """
        {"id":"rv1","brand_name":"Acme","brand_slug":"acme","store_name":null,
         "rating":5,"title":null,"description":"good","review_state":"published",
         "publish_at":"2026-01-01T00:00:00Z","created_at":"2026-01-01T00:00:00Z",
         "points_awarded":0,"hearted":false,"brand_public_reply":null,
         "brand_public_reply_at":null,"dm_thread_id":null,"media":[],"answers":[]}
        """
        let review = try JSONDecoder().decode(MyReview.self, from: Data(json.utf8))
        XCTAssertEqual(review.likeCount, 0)
        XCTAssertFalse(review.likedByMe)
    }
}
