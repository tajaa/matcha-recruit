import Foundation
import Observation

@MainActor
@Observable
final class ReviewsViewModel: LoadableVM {
    var reviews: [CappeReview] = []
    var isLoading = false
    var error: String?

    func load(siteId: String) async {
        await withLoad {
            self.reviews = try await ReviewsService.shared.list(siteId: siteId)
        }
    }

    func setStatus(siteId: String, reviewId: String, status: String) async {
        do {
            let updated = try await ReviewsService.shared.setStatus(siteId: siteId, reviewId: reviewId, status: status)
            if let idx = reviews.firstIndex(where: { $0.id == reviewId }) { reviews[idx] = updated }
        } catch {
            if error.isCancellation { return }
            self.error = error.localizedDescription
        }
    }

    func delete(siteId: String, reviewId: String) async {
        do {
            try await ReviewsService.shared.delete(siteId: siteId, reviewId: reviewId)
            reviews.removeAll { $0.id == reviewId }
        } catch {
            if error.isCancellation { return }
            self.error = error.localizedDescription
        }
    }
}
