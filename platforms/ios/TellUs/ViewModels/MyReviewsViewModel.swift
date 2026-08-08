import Foundation
import Observation

@MainActor
@Observable
final class MyReviewsViewModel: LoadableVM {
    var reviews: [MyReview] = []
    var isLoading = false
    var error: String?
    private var refetchedMediaFor: Set<String> = []

    /// Re-mints expired presigned media URLs by refetching the whole list —
    /// guarded per review id so a genuinely broken media host can't loop.
    func refetchOnceForExpiredMedia(reviewId: String) {
        guard !refetchedMediaFor.contains(reviewId) else { return }
        refetchedMediaFor.insert(reviewId)
        Task { await load() }
    }

    func load() async {
        await withLoad {
            reviews = try await ReviewsService.shared.myReviews()
        }
    }

    func save(id: String, _ patch: MyReviewUpdate) async {
        await withLoad {
            _ = try await ReviewsService.shared.update(id: id, patch)
            reviews = try await ReviewsService.shared.myReviews()
        }
    }

    func withdraw(id: String) async {
        await withLoad {
            try await ReviewsService.shared.withdraw(id: id)
            reviews = try await ReviewsService.shared.myReviews()
        }
    }
}
