import Foundation
import Observation

@MainActor
@Observable
final class MyReviewsViewModel {
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
        isLoading = true; defer { isLoading = false }
        do {
            reviews = try await ReviewsService.shared.myReviews()
            error = nil
        } catch {
            if error.isCancellation { return }
            self.error = error.localizedDescription
        }
    }

    func save(id: String, _ patch: MyReviewUpdate) async {
        error = nil
        do {
            _ = try await ReviewsService.shared.update(id: id, patch)
            await load()
        } catch {
            if error.isCancellation { return }
            self.error = error.localizedDescription
        }
    }

    func withdraw(id: String) async {
        error = nil
        do {
            try await ReviewsService.shared.withdraw(id: id)
            await load()
        } catch {
            if error.isCancellation { return }
            self.error = error.localizedDescription
        }
    }
}
