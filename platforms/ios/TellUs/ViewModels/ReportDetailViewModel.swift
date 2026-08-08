import Foundation
import Observation

@MainActor
@Observable
final class ReportDetailViewModel: LoadableVM {
    let id: String
    var report: Report?
    var isLoading = false
    var error: String?
    /// Guards AsyncMediaImage's onFailure-triggered refetch (re-mints expired
    /// presigned URLs) so a genuinely broken media host can't loop refetches.
    private var didRefetchForExpiredMedia = false

    init(id: String) { self.id = id }

    func refetchOnceForExpiredMedia() {
        guard !didRefetchForExpiredMedia else { return }
        didRefetchForExpiredMedia = true
        Task { await load() }
    }

    func load() async {
        await withLoad {
            report = try await FeedbackService.shared.detail(id: id)
        }
    }

    // Every mutation applies the response Report directly — the server
    // returns the updated row (fresh 15-min media URLs, server-derived
    // fields like review_state/moderation_status included), so a separate
    // refetch is redundant.
    func setStatus(_ status: ReportStatus) async { await run { try await FeedbackService.shared.setStatus(id: self.id, status) } }
    func decideReward(approve: Bool) async { await run { try await FeedbackService.shared.decideReward(id: self.id, approve: approve) } }
    func toggleHeart() async {
        guard let report else { return }
        let hearted = report.hearted_at != nil
        await run {
            hearted ? try await FeedbackService.shared.unheart(id: self.id) : try await FeedbackService.shared.heart(id: self.id)
        }
    }
    func saveReply(_ body: String) async { await run { try await FeedbackService.shared.setReply(id: self.id, body: body) } }
    func deleteReply() async { await run { try await FeedbackService.shared.deleteReply(id: self.id) } }
    func publishNow() async { await run { try await FeedbackService.shared.publishNow(id: self.id) } }

    private func run(_ action: @escaping () async throws -> Report) async {
        error = nil
        do {
            report = try await action()
        } catch {
            if error.isCancellation { return }
            self.error = error.localizedDescription
        }
    }
}
