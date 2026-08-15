import Foundation
import Observation

@MainActor
@Observable
final class BoardManageViewModel: LoadableVM {
    /// nil for a brand account managing its own board; set when a
    /// consumer-typed moderator moderates a specific brand's board.
    let brandId: String?
    /// The board's slug — needed for the Posts tab (GET /boards/{slug} is
    /// the only listing endpoint; server has no /board/manage/posts). Brand
    /// accounts pass their own brand_slug; moderators pass ModeratedBrand.slug.
    /// var, not let — brand_slug can be nil at construction and arrive later
    /// (AppState.refreshWall() swaps `account`, and BrandTabView carries no
    /// `.id()` to force a rebuild), so updateSlug(_:) can correct it in place.
    private(set) var slug: String?
    /// True only when brandId != nil — a moderator's own account is fine
    /// even if the moderated brand's plan lapses, so this never routes to
    /// AppState.brandWall; it's a local, dismissable alert instead.
    var planPausedAlert = false

    var summary: BoardManageSummary?
    var requests: [BoardJoinRequest] = []
    var heldReplies: [BoardManageReplyRow] = []
    var members: [BoardMemberEntry] = []
    var posts: [BoardPost] = []
    var team: [BrandTeamMember] = []
    var loadState = TabLoadState()
    var isLoading = false
    var error: String?

    enum BoardManageError: LocalizedError {
        case missingSlug
        var errorDescription: String? {
            "Couldn't figure out which brand's board to show. Try reopening this tab."
        }
    }

    init(brandId: String?, slug: String? = nil) {
        self.brandId = brandId
        self.slug = slug
    }

    /// Sets a slug that arrived after construction and invalidates the
    /// Posts tab so the next visit refetches instead of showing a stale
    /// "No posts yet" (or the missingSlug error) forever. No-op when the
    /// slug hasn't actually changed.
    func updateSlug(_ newSlug: String?) {
        guard newSlug != slug else { return }
        slug = newSlug
        posts = []
        loadState.invalidate(.posts)
    }

    func loadSummary() async {
        summary = (try? await BoardManageService.shared.summary(brandId: brandId)) ?? summary
    }

    /// One entry point for every sub-tab. Idempotent — an already-loaded tab
    /// is a no-op unless forced, so `.task(id: tab)` firing again on every
    /// Picker tap is free.
    func loadTab(_ tab: BoardTab, force: Bool = false) async {
        guard loadState.begin(tab, force: force) else { return }
        let outcome = await withLoad {
            switch tab {
            case .requests:
                self.requests = try await BoardManageService.shared.requests(brandId: self.brandId)
            case .held:
                self.heldReplies = try await BoardManageService.shared.heldReplies(brandId: self.brandId)
            case .members:
                self.members = try await BoardManageService.shared.members(brandId: self.brandId)
            case .team:
                self.team = try await BoardManageService.shared.team(brandId: self.brandId)
            case .posts:
                // Was `guard let slug else { return }` — a silent no-op that
                // looked exactly like an empty board. Fail loudly instead.
                guard let slug = self.slug else { throw BoardManageError.missingSlug }
                self.posts = try await BoardService.shared.board(slug: slug, limit: 50).posts
            }
        }
        switch outcome {
        case .success: loadState.succeed(tab)
        case .cancelled: loadState.cancel(tab)
        case .failed: loadState.fail(tab)
        }
    }

    func refresh(_ tab: BoardTab) async {
        await loadSummary()
        await loadTab(tab, force: true)
    }

    func updatePost(_ id: String, _ body: BoardPostUpdate) async {
        await run({
            let updated = try await BoardManageService.shared.updatePost(id: id, brandId: self.brandId, body)
            if let idx = self.posts.firstIndex(where: { $0.id == id }) { self.posts[idx] = updated }
        }) {}
    }

    func addTeamMember(email: String) async {
        await run({
            let member = try await BoardManageService.shared.addTeamMember(email: email, brandId: self.brandId)
            self.team.append(member)
        }) {}
    }

    func removeTeamMember(_ id: String) async {
        await run({ try await BoardManageService.shared.removeTeamMember(id: id, brandId: self.brandId) }) {
            self.team.removeAll { $0.id == id }
        }
    }

    func setInboxAccess(memberID: String, enabled: Bool) async {
        do {
            try await DmService.shared.setTeamInboxAccess(memberID: memberID, enabled: enabled)
            if let index = team.firstIndex(where: { $0.id == memberID }) {
                let member = team[index]
                team[index] = BrandTeamMember(
                    id: member.id, account_display_name: member.account_display_name,
                    email: member.email, role: member.role, can_manage_inbox: enabled
                )
            }
        } catch {
            if !error.isCancellation { self.error = error.localizedDescription }
        }
    }

    func approveRequest(_ id: String) async {
        await run({ try await BoardManageService.shared.approveRequest(id: id, brandId: self.brandId) }) {
            self.requests.removeAll { $0.id == id }
        }
    }

    func declineRequest(_ id: String) async {
        await run({ try await BoardManageService.shared.declineRequest(id: id, brandId: self.brandId) }) {
            self.requests.removeAll { $0.id == id }
        }
    }

    func removeMember(_ id: String) async {
        await run({ try await BoardManageService.shared.removeMember(id: id, brandId: self.brandId) }) {
            self.members.removeAll { $0.id == id }
        }
    }

    func approveReply(_ id: String) async {
        await run({ try await BoardManageService.shared.approveReply(id: id, brandId: self.brandId) }) {
            self.heldReplies.removeAll { $0.id == id }
        }
    }

    func rejectReply(_ id: String) async {
        await run({ try await BoardManageService.shared.rejectReply(id: id, brandId: self.brandId) }) {
            self.heldReplies.removeAll { $0.id == id }
        }
    }

    func createPost(_ body: BoardPostCreate) async {
        await run({
            let created = try await BoardManageService.shared.createPost(brandId: self.brandId, body)
            self.posts.insert(created, at: 0)
        }) {}
    }

    func deletePost(_ id: String) async {
        await run({ try await BoardManageService.shared.deletePost(id: id, brandId: self.brandId) }) {
            self.posts.removeAll { $0.id == id }
        }
    }

    /// Runs a mutation and applies a targeted local update on success instead
    /// of refetching every tab — refetching a tab wholesale is reserved for
    /// .task(id:)/.refreshable. Still refreshes the summary's counters
    /// (cheap, single endpoint) so the header badges track.
    private func run(_ action: @escaping () async throws -> Void, onSuccess: @escaping @MainActor () -> Void) async {
        error = nil
        do {
            try await action()
            onSuccess()
            await loadSummary()
        } catch APIError.paymentRequired {
            if brandId != nil {
                planPausedAlert = true
            } else {
                error = "This brand's plan isn't active."
            }
        } catch let APIError.httpError(409, _) {
            // Another moderator already acted on this row — refetch the
            // queue it came from instead of leaving a stale row on screen.
            // Must run AFTER the refetch: loadTab's withLoad clears error
            // to nil on success, which was wiping this message immediately.
            await loadTab(.held, force: true)
            await loadTab(.requests, force: true)
            error = "Already moderated — refreshing."
        } catch {
            if error.isCancellation { return }
            self.error = error.localizedDescription
        }
    }
}
