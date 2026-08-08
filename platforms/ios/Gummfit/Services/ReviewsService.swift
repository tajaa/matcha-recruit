import Foundation

/// Review moderation (server/app/cappe/routes/reviews.py). Public submission +
/// the storefront feed live server-side only — this is the owner moderation
/// surface.
final class ReviewsService {
    static let shared = ReviewsService()
    private init() {}

    func list(siteId: String) async throws -> [CappeReview] {
        try await APIClient.shared.request(method: "GET", path: "/sites/\(siteId)/reviews")
    }

    func setStatus(siteId: String, reviewId: String, status: String) async throws -> CappeReview {
        try await APIClient.shared.request(
            method: "PATCH", path: "/sites/\(siteId)/reviews/\(reviewId)",
            body: CappeReviewModerate(status: status)
        )
    }

    func delete(siteId: String, reviewId: String) async throws {
        try await APIClient.shared.requestVoid(method: "DELETE", path: "/sites/\(siteId)/reviews/\(reviewId)")
    }
}
