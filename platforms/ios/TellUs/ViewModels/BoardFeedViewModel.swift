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
    var boardPaused = false
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
            boardPaused = false
            error = nil
        } catch APIError.httpError(409, let message) where message == "This board is paused." {
            markPausedBoard()
        } catch APIError.httpError(403, _) {
            boardPaused = false
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

    /// The join endpoint has already persisted a pending membership when it
    /// returns success, so the feed can update immediately without a second
    /// board request that is expected to return 403 until approval.
    func markPendingMembership() {
        page = nil
        notAMember = true
        membershipStatus = .pending
        boardPaused = false
        error = nil
    }

    /// Show why a non-member cannot request access. Paused boards do not have
    /// a pending membership, so the join CTA must not remain available.
    func markPausedBoard() {
        page = nil
        notAMember = true
        membershipStatus = nil
        boardPaused = true
        error = nil
    }

    func requestJoin() async {
        do {
            try await BoardService.shared.join(slug: slug, note: nil)
            markPendingMembership()
        } catch APIError.httpError(409, let message) {
            if message == "Request already pending" {
                // This is a successful user-visible outcome: the request is
                // already in the queue. Avoid GET /boards (403) and relying
                // on a second membership lookup just to rediscover pending.
                markPendingMembership()
            } else if message == "This board is paused." {
                markPausedBoard()
            } else {
                // Declined/removed and other board conflicts still need the
                // normal status derivation path.
                await load()
            }
        } catch {
            if error.isCancellation { return }
            self.error = error.localizedDescription
            return
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
