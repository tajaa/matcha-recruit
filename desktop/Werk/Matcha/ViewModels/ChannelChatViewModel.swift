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
        // Wipe any stale closure from a prior channel BEFORE the await on
        // loadChannel. Otherwise the previous channel's `onMessage` (whose
        // captured `channelId` guard still passes for that prior channel) can
        // fire during this view's REST fetch and append a stale-channel
        // message into the just-replaced `messages` array.
        ws.clearCallbacks()
        cancelAllPendingTimeouts()
        self.channelId = channelId
        await loadChannel(channelId: channelId)
        wireCallbacks(channelId: channelId)
        ws.connect()
        ws.joinRoom(channelId: channelId)
    }

    func stop(channelId: String) {
        ws.clearCallbacksIfRoomMatches(channelId)
        cancelAllPendingTimeouts()
    }

    private func cancelAllPendingTimeouts() {
        for task in pendingFailureTasks.values { task.cancel() }
        pendingFailureTasks.removeAll()
    }

    func loadChannel(channelId: String) async {
        isLoading = true
        errorMessage = nil
        do {
            let detail = try await service.getChannel(id: channelId)
            channel = detail
            ws.setCurrentRoomName(detail.name)
            messages = detail.messages
            isLoading = false
        } catch {
            errorMessage = error.localizedDescription
            isLoading = false
        }
    }

    private func wireCallbacks(channelId: String) {
        // Closures capture `self` (a class) by reference — mutations propagate
        // to the live SwiftUI view via @Observable tracking.
        ws.onMessage = { [weak self] msg in
            guard let self, msg.channelId == channelId else { return }
            // Reconcile optimistic-pending entries first. The sender's own echo
            // carries the client_message_id we generated on send; replace the
            // pending struct (whose `id` was the client UUID) with the
            // server-confirmed one so the row keeps its position but flips
            // pending=false and gets the real server id + timestamp.
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
        ws.onMessageDeleted = { [weak self] messageId, deletedBy in
            guard let self else { return }
            if let idx = self.messages.firstIndex(where: { $0.id == messageId }) {
                self.messages[idx].deletedAt = ISO8601DateFormatter().string(from: Date())
                self.messages[idx].deletedBy = deletedBy
            }
        }
        ws.onReactionUpdate = { [weak self] messageId, reactions in
            guard let self else { return }
            if let idx = self.messages.firstIndex(where: { $0.id == messageId }) {
                self.messages[idx].reactions = reactions
            }
        }
        ws.onOnlineUsers = { [weak self] users in
            self?.onlineUsers = users
        }
        ws.onUserJoined = { [weak self] user in
            guard let self else { return }
            if !self.onlineUsers.contains(where: { $0.id == user.id }) {
                self.onlineUsers.append(user)
            }
        }
        ws.onUserLeft = { [weak self] user in
            self?.onlineUsers.removeAll { $0.id == user.id }
        }
        ws.onTyping = { [weak self] userId, name in
            guard let self else { return }
            self.typingUsers[userId] = name.lowercased().replacingOccurrences(of: " ", with: "_")
            self.typingClearTask?.cancel()
            self.typingClearTask = Task { [weak self] in
                try? await Task.sleep(for: .seconds(3))
                self?.typingUsers.removeValue(forKey: userId)
            }
        }
        ws.onError = { [weak self] msg in
            self?.errorMessage = msg
        }
    }
}
