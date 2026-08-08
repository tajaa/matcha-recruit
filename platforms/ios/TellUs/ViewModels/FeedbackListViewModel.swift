import Foundation
import Observation

@MainActor
@Observable
final class FeedbackListViewModel: LoadableVM {
    var reports: [Report] = []
    var stats: FeedbackStats?
    var statusFilter: ReportStatus?
    var sentimentFilter: Sentiment?
    var isLoading = false
    var error: String?
    var hasMore = true

    private let pageSize: Int
    private var offset = 0

    init(pageSize: Int = 25) { self.pageSize = pageSize }

    func load(reset: Bool) async {
        if !reset && isLoading { return }   // in-flight guard: avoids duplicate pages from a fast double onAppear
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
        do {
            stats = try await FeedbackService.shared.stats()
        } catch {
            if error.isCancellation { return }
            // Stats are supplementary to the report list — a failure here
            // shouldn't blank out the (separately loaded) list or its error
            // banner, so this is intentionally silent beyond the console.
            NSLog("[FeedbackListViewModel] loadStats failed: \(error.localizedDescription)")
        }
    }
}
