import Foundation
import Observation

@MainActor
@Observable
final class ReportDetailViewModel {
    let id: String
    var report: Report?
    var isLoading = false
    var error: String?

    init(id: String) { self.id = id }

    func load() async {
        isLoading = true; defer { isLoading = false }
        do {
            report = try await FeedbackService.shared.detail(id: id)
            error = nil
        } catch {
            if error.isCancellation { return }
            self.error = error.localizedDescription
        }
    }

    // Every mutation refetches — re-mints the 15-min media URLs and picks up
    // server-derived fields (review_state, moderation_status) in one place.
    func setStatus(_ status: ReportStatus) async { await run { try await FeedbackService.shared.setStatus(id: self.id, status) } }
    func decideReward(approve: Bool) async { await run { try await FeedbackService.shared.decideReward(id: self.id, approve: approve) } }
    func toggleHeart() async {
        guard let report else { return }
        let hearted = report.hearted_at != nil
        await run {
            if hearted { try await FeedbackService.shared.unheart(id: self.id) }
            else { try await FeedbackService.shared.heart(id: self.id) }
        }
    }
    func saveReply(_ body: String) async { await run { try await FeedbackService.shared.setReply(id: self.id, body: body) } }
    func deleteReply() async { await run { try await FeedbackService.shared.deleteReply(id: self.id) } }
    func publishNow() async { await run { try await FeedbackService.shared.publishNow(id: self.id) } }

    private func run(_ action: @escaping () async throws -> Void) async {
        error = nil
        do {
            try await action()
            await load()
        } catch {
            if error.isCancellation { return }
            self.error = error.localizedDescription
        }
    }
}
