import Foundation
import Observation

@MainActor
@Observable
final class BoardFeedViewModel: LoadableVM {
    let slug: String
    var page: BoardPage?
    var repliesByPost: [String: [BoardReply]] = [:]
    var isLoading = false
    var error: String?
    var notAMember = false
    /// Set only once `notAMember` is true — distinguishes "never requested"
    /// from "request sent, awaiting the brand's approval" so the locked
    /// screen doesn't keep offering a re-tappable join button that just
    /// 409s server-side.
    var membershipStatus: BoardMembershipStatus?
    let redeemFlow = RedeemFlowModel()

    init(slug: String) { self.slug = slug }

    // Custom (not withLoad): a 403 here means "not a member yet", a
    // recoverable state distinct from a generic error banner.
    func load() async {
        isLoading = true; defer { isLoading = false }
        do {
            page = try await BoardService.shared.board(slug: slug)
            notAMember = false
            membershipStatus = nil
            error = nil
        } catch APIError.httpError(403, _) {
            notAMember = true
            await refreshMembershipStatus()
        } catch {
            if error.isCancellation { return }
            self.error = error.localizedDescription
        }
    }

    private func refreshMembershipStatus() async {
        membershipStatus = try? await BoardService.shared.memberships()
            .first { $0.brand_slug == slug }?.status
    }

    func requestJoin() async {
        do {
            try await BoardService.shared.join(slug: slug, note: nil)
        } catch APIError.httpError(409, _) {
            // Already pending/declined server-side — fall through to load(),
            // which re-derives the real status below.
        } catch {
            if error.isCancellation { return }
            self.error = error.localizedDescription
            return
        }
        await load()
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
