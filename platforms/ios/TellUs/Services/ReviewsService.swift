import Foundation

final class ReviewsService {
    static let shared = ReviewsService()
    private let client = APIClient.shared
    private init() {}

    func myReviews(limit: Int = 50, offset: Int = 0) async throws -> [MyReview] {
        try await client.request(method: "GET", path: "/me/reviews?limit=\(limit)&offset=\(offset)")
    }

    /// PATCH only valid while review_state == held and pre-publish — server
    /// 409s otherwise.
    func update(id: String, _ patch: MyReviewUpdate) async throws -> MyReview {
        try await client.request(method: "PATCH", path: "/me/reviews/\(id)", body: patch)
    }

    func withdraw(id: String) async throws {
        try await client.requestVoid(method: "POST", path: "/me/reviews/\(id)/withdraw")
    }
}
