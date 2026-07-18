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

    func loadChannel(channelId: String, isRefresh: Bool = false) async {
        if !isRefresh { isLoading = true }   // refresh stays silent — no loading flash
        errorMessage = nil
        do {
            let detail = try await service.getChannel(id: channelId)
            channel = detail
            ws.setCurrentRoomName(detail.name)
            if isRefresh {
                // Silent merge: keep local optimistic rows the server echo hasn't
                // replaced yet, and only reassign when the id list actually
                // changed (identical reassignment would rebuild the list = flash).
                let pendingExtras = messages.filter { m in
                    (m.pending || m.failed) && !detail.messages.contains(where: { $0.id == m.id })
                }
                let merged = detail.messages + pendingExtras
                if merged.map(\.id) != messages.map(\.id) { messages = merged }
            } else {
                messages = detail.messages
                // A full page back means there may be older history to page in.
                hasMoreHistory = detail.messages.count >= historyPageSize
                isLoading = false
            }
        } catch {
            errorMessage = error.localizedDescription
            if !isRefresh { isLoading = false }
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
            if older.count < historyPageSize { hasMoreHistory = false }
            let existingIds = Set(messages.map(\.id))
            let fresh = older.filter { !existingIds.contains($0.id) }
            if fresh.isEmpty {
                hasMoreHistory = false
            } else {
                messages.insert(contentsOf: fresh, at: 0)
            }
        } catch {
            errorMessage = error.localizedDescription
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
