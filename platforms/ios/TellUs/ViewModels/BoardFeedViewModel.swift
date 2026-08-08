import Foundation
import Observation

@MainActor
@Observable
final class BoardFeedViewModel {
    let slug: String
    var page: BoardPage?
    var repliesByPost: [String: [BoardReply]] = [:]
    var isLoading = false
    var error: String?
    var notAMember = false
    let redeemFlow = RedeemFlowModel()

    init(slug: String) { self.slug = slug }

    func load() async {
        isLoading = true; defer { isLoading = false }
        do {
            page = try await BoardService.shared.board(slug: slug)
            notAMember = false
            error = nil
        } catch APIError.httpError(403, _) {
            notAMember = true
        } catch {
            if error.isCancellation { return }
            self.error = error.localizedDescription
        }
    }

    func loadReplies(postId: String) async {
        do {
            repliesByPost[postId] = try await BoardService.shared.replies(slug: slug, postId: postId)
        } catch {
            if error.isCancellation { return }
            self.error = error.localizedDescription
        }
    }

    func reply(postId: String, body: String) async {
        do {
            _ = try await BoardService.shared.reply(slug: slug, postId: postId, body: body)
            await loadReplies(postId: postId)
        } catch {
            if error.isCancellation { return }
            self.error = error.localizedDescription
        }
    }

    func deleteOwnReply(postId: String, replyId: String) async {
        do {
            try await BoardService.shared.deleteOwnReply(slug: slug, replyId: replyId)
            await loadReplies(postId: postId)
        } catch {
            if error.isCancellation { return }
            self.error = error.localizedDescription
        }
    }

}
