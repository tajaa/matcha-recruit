import Foundation
import Observation

@MainActor
@Observable
final class FeedbackListViewModel {
    var reports: [Report] = []
    var stats: FeedbackStats?
    var statusFilter: ReportStatus?
    var sentimentFilter: Sentiment?
    var isLoading = false
    var error: String?
    var hasMore = true

    private let pageSize = 25
    private var offset = 0

    func load(reset: Bool) async {
        if reset { offset = 0; hasMore = true }
        guard hasMore || reset else { return }
        isLoading = true; defer { isLoading = false }
        do {
            let page = try await FeedbackService.shared.list(
                status: statusFilter, sentiment: sentimentFilter, limit: pageSize, offset: offset
            )
            reports = reset ? page : reports + page
            hasMore = page.count == pageSize
            offset += page.count
            error = nil
        } catch {
            if error.isCancellation { return }
            self.error = error.localizedDescription
        }
    }

    func loadStats() async {
        stats = try? await FeedbackService.shared.stats()
    }
}
