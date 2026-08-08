import Foundation
import Observation

@MainActor
@Observable
final class BoardManageViewModel {
    /// nil for a brand account managing its own board; set when a
    /// consumer-typed moderator moderates a specific brand's board.
    let brandId: String?
    /// True only when brandId != nil — a moderator's own account is fine
    /// even if the moderated brand's plan lapses, so this never routes to
    /// AppState.brandWall; it's a local, dismissable alert instead.
    var planPausedAlert = false

    var summary: BoardManageSummary?
    var requests: [BoardJoinRequest] = []
    var heldReplies: [BoardManageReplyRow] = []
    var members: [BoardMemberEntry] = []
    var isLoading = false
    var error: String?

    init(brandId: String?) { self.brandId = brandId }

    func load() async {
        isLoading = true; defer { isLoading = false }
        do {
            async let s = BoardManageService.shared.summary(brandId: brandId)
            async let r = BoardManageService.shared.requests(brandId: brandId)
            async let h = BoardManageService.shared.heldReplies(brandId: brandId)
            async let m = BoardManageService.shared.members(brandId: brandId)
            summary = try await s
            requests = try await r
            heldReplies = try await h
            members = try await m
            error = nil
        } catch {
            if error.isCancellation { return }
            self.error = error.localizedDescription
        }
    }

    func approveRequest(_ id: String) async { await run { try await BoardManageService.shared.approveRequest(id: id, brandId: self.brandId) } }
    func declineRequest(_ id: String) async { await run { try await BoardManageService.shared.declineRequest(id: id, brandId: self.brandId) } }
    func removeMember(_ id: String) async { await run { try await BoardManageService.shared.removeMember(id: id, brandId: self.brandId) } }
    func approveReply(_ id: String) async { await run { try await BoardManageService.shared.approveReply(id: id, brandId: self.brandId) } }
    func rejectReply(_ id: String) async { await run { try await BoardManageService.shared.rejectReply(id: id, brandId: self.brandId) } }

    func createPost(_ body: BoardPostCreate) async {
        await run { _ = try await BoardManageService.shared.createPost(brandId: self.brandId, body) }
    }

    func deletePost(_ id: String) async { await run { try await BoardManageService.shared.deletePost(id: id, brandId: self.brandId) } }

    private func run(_ action: @escaping () async throws -> Void) async {
        error = nil
        do {
            try await action()
            await load()
        } catch APIError.paymentRequired {
            if brandId != nil {
                planPausedAlert = true
            } else {
                error = "This brand's plan isn't active."
            }
        } catch {
            if error.isCancellation { return }
            self.error = error.localizedDescription
        }
    }
}
