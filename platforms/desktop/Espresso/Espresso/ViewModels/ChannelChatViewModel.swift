import Foundation

@Observable
@MainActor
final class ChannelChatViewModel {
    var channel: ChannelDetail?
    var messages: [ChannelMessage] = []
    var onlineUsers: [ChannelOnlineUser] = []
    var typingUsers: [String: String] = [:]
    var isLoading = true
    var errorMessage: String?
    /// History pagination. The channel-detail endpoint only embeds the newest
    /// page, so older history is fetched on demand via `getMessages(before:)`.
    var hasMoreHistory = false
    var isLoadingOlder = false
    /// Bumped when a silent refresh merge changes the list — the view watches
    /// this to scroll to the latest message. Needed because the scroll trigger
    /// keys on the LAST message's identity (so history prepends don't yank the
    /// view down), which misses merges that add messages above a pending/
    /// failed row stuck at the tail.
    var scrollToLatestTick = 0
    /// Mirrors the server's page size: both `getMessages`' default limit and
    /// the newest-page embed in the channel-detail endpoint (channels.py) are
    /// 50. The full-page heuristic below assumes these agree.
    private let historyPageSize = 50

    private(set) var channelId: String?
    private var typingClearTask: Task<Void, Never>?
    /// Pending-message failure timers, keyed by client_message_id. Started in
    /// `schedulePendingTimeout(...)` when the view does an optimistic append;
    /// cancelled in the WS `onMessage` reconciliation path. After 8s with no
    /// echo, flips the message to `failed=true, pending=false` so the user
    /// sees a clear "didn't send" affordance instead of an opacity-dim row
    /// that hangs forever.
    private var pendingFailureTasks: [String: Task<Void, Never>] = [:]
    private static let pendingFailureSeconds: UInt64 = 8
    private let ws = ChannelsWebSocket.shared
    private let service = ChannelsService.shared
    /// This VM's registration token on the shared socket. Each channel view owns
    /// its own subscription, so a second view wiring up can no longer steal this
    /// one's message echoes (the bug that flipped collab-chat sends to "failed").
    private var wsToken: UUID?

    private func unsubscribeFromWS() {
        if let token = wsToken {
            ws.unsubscribe(token)
            wsToken = nil
        }
    }

    /// Called by ChannelDetailView right after an optimistic-pending entry is
    /// appended to `messages`. Starts an 8s timer; if the WS echo doesn't
    /// arrive first, marks the row failed.
    func schedulePendingTimeout(clientMessageId cmid: String) {
        pendingFailureTasks[cmid]?.cancel()
        pendingFailureTasks[cmid] = Task { [weak self] in
            try? await Task.sleep(for: .seconds(Int(Self.pendingFailureSeconds)))
            guard let self, !Task.isCancelled else { return }
            self.markPendingAsFailed(cmid: cmid)
            self.pendingFailureTasks.removeValue(forKey: cmid)
        }
    }

    private func cancelPendingTimeout(clientMessageId cmid: String) {
        pendingFailureTasks.removeValue(forKey: cmid)?.cancel()
    }

    private func markPendingAsFailed(cmid: String) {
        if let idx = messages.firstIndex(where: { $0.clientMessageId == cmid && $0.pending }) {
            messages[idx].pending = false
            messages[idx].failed = true
        }
    }

    func start(channelId: String) async {
        // Drop any prior subscription BEFORE the await on loadChannel, so a
        // stale closure from a previous channel can't fire during this view's
        // REST fetch and append into the just-replaced `messages` array.
        unsubscribeFromWS()
        cancelAllPendingTimeouts()
        self.channelId = channelId
        await loadChannel(channelId: channelId)
        wireCallbacks(channelId: channelId)
        ws.connect()
        ws.joinRoom(channelId: channelId)
    }

    /// Warm re-entry: this VM was kept alive (WorkDetailVMStore) and already
    /// holds this channel. Re-wire the WS room and silently revalidate, instead
    /// of a cold `start` (which blanks messages and flashes the loader). Falls
    /// back to a full `start` if the VM isn't actually warm for this channel.
    func resume(channelId: String) async {
        guard self.channelId == channelId, channel != nil else {
            await start(channelId: channelId)
            return
        }
        unsubscribeFromWS()
        cancelAllPendingTimeouts()
        wireCallbacks(channelId: channelId)
        ws.connect()
        ws.joinRoom(channelId: channelId)
        await loadChannel(channelId: channelId, isRefresh: true)
    }

    func stop(channelId: String) {
        unsubscribeFromWS()
        cancelAllPendingTimeouts()
    }

    private func cancelAllPendingTimeouts() {
        for task in pendingFailureTasks.values { task.cancel() }
        pendingFailureTasks.removeAll()
    }

    /// Outcome of folding a freshly-fetched newest page into the on-screen
    /// list. Pure data so `refreshMerge` can be unit-tested without a socket,
    /// a service, or a live channel.
    struct RefreshMerge: Equatable {
        /// The list to display. Only meaningful when `changed` is true —
        /// reassigning an identical list rebuilds the view (visible flash).
        var messages: [ChannelMessage]
        var hasMoreHistory: Bool
        /// Whether the merge changed the id sequence, i.e. whether to assign.
        var changed: Bool
        /// Whether to bump `scrollToLatestTick`.
        var scrollToLatest: Bool
    }

    /// Fold a refreshed newest page into the current list.
    ///
    /// Keeps local optimistic rows the server echo hasn't replaced yet, and
    /// preserves history paged in via `loadOlder()` — the chronological prefix
    /// of the current list that predates the newest page. Replacing the array
    /// with just the newest page would yank paged-in messages out from under
    /// the reader and strand `hasMoreHistory`.
    ///
    /// If nothing overlaps the newest page, more than a full page arrived while
    /// away — the gap between the kept history and the newest page would be
    /// unknowable, so it falls back to the newest page alone and recomputes the
    /// flag.
    ///
    /// Known cosmetic edge: a pending/failed row that drifted mid-list (WS rows
    /// appended after it) re-sorts to the tail here — positional preservation
    /// would need timestamp interleaving, deliberately not attempted.
    ///
    /// `nonisolated` so tests can call it off the main actor; it touches no
    /// instance state.
    nonisolated static func refreshMerge(
        existing: [ChannelMessage],
        newest: [ChannelMessage],
        hasMoreHistory: Bool,
        pageSize: Int
    ) -> RefreshMerge {
        let serverIds = Set(newest.map(\.id))
        let pendingExtras = existing.filter { m in
            (m.pending || m.failed) && !serverIds.contains(m.id)
        }
        let overlaps = existing.contains { serverIds.contains($0.id) }
        let olderPrefix = overlaps
            ? Array(existing.prefix { !serverIds.contains($0.id) && !$0.pending && !$0.failed })
            : []
        let resolvedHasMore = overlaps ? hasMoreHistory : newest.count >= pageSize

        let oldIds = Set(existing.map(\.id))
        let hasNewMessages = newest.contains { !oldIds.contains($0.id) }
        let merged = olderPrefix + newest + pendingExtras
        let changed = merged.map(\.id) != existing.map(\.id)

        // The tail may be an unchanged pending/failed row, so the view's
        // last-identity scroll trigger can't see newly arrived messages —
        // signal it explicitly. ONLY when new messages actually arrived AND the
        // tail is pinned: a deletion-only or reorder-only merge must not yank a
        // reader out of the history they're reading, and a changed tail is
        // already handled by the identity trigger.
        let tailUnchanged = merged.last?.stableKey == existing.last?.stableKey

        return RefreshMerge(
            messages: merged,
            hasMoreHistory: resolvedHasMore,
            changed: changed,
            scrollToLatest: changed && tailUnchanged && hasNewMessages
        )
    }

    /// Outcome of folding a fetched older page into the head of the list.
    struct OlderPageMerge: Equatable {
        /// Messages to prepend, with anything already on screen filtered out.
        var fresh: [ChannelMessage]
        var hasMoreHistory: Bool
    }

    /// Dedup a fetched older page against what's already on screen and restate
    /// the end-of-history policy: a short page or an all-duplicates page means
    /// the end was reached.
    ///
    /// `nonisolated` so tests can call it off the main actor; it touches no
    /// instance state.
    nonisolated static func olderPageMerge(
        existing: [ChannelMessage],
        older: [ChannelMessage],
        pageSize: Int
    ) -> OlderPageMerge {
        let existingIds = Set(existing.map(\.id))
        let fresh = older.filter { !existingIds.contains($0.id) }
        return OlderPageMerge(
            fresh: fresh,
            hasMoreHistory: older.count >= pageSize && !fresh.isEmpty
        )
    }

    func loadChannel(channelId: String, isRefresh: Bool = false) async {
        if !isRefresh { isLoading = true }   // refresh stays silent — no loading flash
        errorMessage = nil
        do {
            let detail = try await service.getChannel(id: channelId)
            channel = detail
            ws.setCurrentRoomName(detail.name)
            if isRefresh {
                let merge = Self.refreshMerge(
                    existing: messages,
                    newest: detail.messages,
                    hasMoreHistory: hasMoreHistory,
                    pageSize: historyPageSize
                )
                hasMoreHistory = merge.hasMoreHistory
                if merge.changed {
                    messages = merge.messages
                    if merge.scrollToLatest { scrollToLatestTick &+= 1 }
                }
            } else {
                messages = detail.messages
                // A full page back means there may be older history to page in.
                hasMoreHistory = detail.messages.count >= historyPageSize
                isLoading = false
            }
        } catch {
            // Always clear the cold-load spinner, even on cancellation —
            // an early return that leaves isLoading stuck true would show a
            // phantom loading state on a warm cached VM.
            if !isRefresh { isLoading = false }
            if error.isCancellation { return }
            if isRefresh {
                // A PERMANENT failure on a silent refresh means the channel
                // is gone for this user (deleted server-side / kicked) —
                // there is no WS event for either, so this is the only
                // signal. Surface it: the full-pane error state is correct
                // for a dead channel. Transient failures stay silent — they
                // must not blank a healthy, already-loaded chat.
                if case APIError.httpError(let code, _) = error, code == 403 || code == 404 {
                    errorMessage = error.localizedDescription
                }
                return
            }
            // Cold loads always surface the failure (nothing else on screen).
            errorMessage = error.localizedDescription
        }
    }

    /// Fetch the page of messages immediately older than the current oldest and
    /// prepend them. No-op while already loading or once a short page confirms
    /// there is no more history. Without this, `getMessages(before:)` had zero
    /// callers and channels with >50 messages silently truncated to the newest
    /// page with no way to reach older history.
    func loadOlder() async {
        guard hasMoreHistory, !isLoadingOlder,
              let channelId, let oldest = messages.first else { return }
        isLoadingOlder = true
        defer { isLoadingOlder = false }
        do {
            let older = try await service.getMessages(channelId: channelId, before: oldest.createdAt, limit: historyPageSize)
            // The list may have been REPLACED while the fetch was in flight —
            // a silent refresh merge on refocus can take its no-overlap
            // fallback and reset to the newest page. If the anchor row this
            // page was fetched against is no longer the head, splicing the
            // stale page in would leave an unfillable mid-list gap; drop it.
            // The button remains and re-pages consistently off the new head.
            guard messages.first?.id == oldest.id else { return }
            let page = Self.olderPageMerge(existing: messages, older: older, pageSize: historyPageSize)
            hasMoreHistory = page.hasMoreHistory
            messages.insert(contentsOf: page.fresh, at: 0)
        } catch {
            if error.isCancellation { return }
            // Deliberately NOT errorMessage: the view treats that as a fatal
            // whole-pane error state, which would replace a healthy loaded
            // chat because one history page failed. hasMoreHistory stays true,
            // so the button itself remains as the retry affordance.
            print("[ChannelChat] loadOlder failed: \(error)")
        }
    }

    /// Edit an existing message. Optimistic: update content + editedAt locally,
    /// then PATCH; revert on failure. The server enforces the 15-min window.
    func editMessage(_ msg: ChannelMessage, newContent: String) async {
        let trimmed = newContent.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, trimmed != msg.content,
              let idx = messages.firstIndex(where: { $0.id == msg.id }) else { return }
        let previous = messages[idx].content
        messages[idx].content = trimmed
        messages[idx].editedAt = ISO8601DateFormatter().string(from: Date())
        do {
            try await service.editMessage(channelId: msg.channelId, messageId: msg.id, content: trimmed)
        } catch {
            if let i = messages.firstIndex(where: { $0.id == msg.id }) {
                messages[i].content = previous
            }
            errorMessage = error.localizedDescription
        }
    }

    private func wireCallbacks(channelId: String) {
        // Replace any existing subscription, then register a fresh one. Closures
        // capture `self` (a class) by reference — mutations propagate to the
        // live SwiftUI view via @Observable tracking. Every handler self-filters
        // by `channelId` since the socket fans out to all subscribers.
        unsubscribeFromWS()
        var sub = ChannelSubscriber()
        sub.onMessage = { [weak self] msg in
            guard let self, msg.channelId == channelId else { return }
            // Reconcile optimistic-pending entries first. The sender's own echo
            // carries the client_message_id we generated on send; replace the
            // pending struct (whose `id` was the client UUID) with the
            // server-confirmed one so the row keeps its position but flips
            // pending=false and gets the real server id + timestamp. Matching
            // `failed` rows too means a resent message auto-heals a red row.
            if let cmid = msg.clientMessageId, !cmid.isEmpty,
               let idx = self.messages.firstIndex(where: { $0.clientMessageId == cmid && ($0.pending || $0.failed) }) {
                self.cancelPendingTimeout(clientMessageId: cmid)
                self.messages[idx] = msg
                return
            }
            // Normal dedup by server id (handles reconnect replays and other
            // senders' messages).
            if !self.messages.contains(where: { $0.id == msg.id }) {
                self.messages.append(msg)
            }
        }
        sub.onMessageDeleted = { [weak self] messageId, deletedBy in
            guard let self else { return }
            if let idx = self.messages.firstIndex(where: { $0.id == messageId }) {
                self.messages[idx].deletedAt = ISO8601DateFormatter().string(from: Date())
                self.messages[idx].deletedBy = deletedBy
            }
        }
        sub.onMessageEdited = { [weak self] messageId, content, editedAt in
            guard let self else { return }
            if let idx = self.messages.firstIndex(where: { $0.id == messageId }) {
                self.messages[idx].content = content
                self.messages[idx].editedAt = editedAt ?? ISO8601DateFormatter().string(from: Date())
            }
        }
        sub.onReactionUpdate = { [weak self] messageId, reactions in
            guard let self else { return }
            if let idx = self.messages.firstIndex(where: { $0.id == messageId }) {
                self.messages[idx].reactions = reactions
            }
        }
        sub.onOnlineUsers = { [weak self] users in
            self?.onlineUsers = users
        }
        sub.onUserJoined = { [weak self] user in
            guard let self else { return }
            if !self.onlineUsers.contains(where: { $0.id == user.id }) {
                self.onlineUsers.append(user)
            }
        }
        sub.onUserLeft = { [weak self] user in
            self?.onlineUsers.removeAll { $0.id == user.id }
        }
        sub.onTyping = { [weak self] userId, name in
            guard let self else { return }
            self.typingUsers[userId] = name.lowercased().replacingOccurrences(of: " ", with: "_")
            self.typingClearTask?.cancel()
            self.typingClearTask = Task { [weak self] in
                try? await Task.sleep(for: .seconds(3))
                self?.typingUsers.removeValue(forKey: userId)
            }
        }
        sub.onError = { [weak self] msg in
            self?.errorMessage = msg
        }
        wsToken = ws.subscribe(sub)
    }
}
