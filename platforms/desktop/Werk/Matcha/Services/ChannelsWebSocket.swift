import Foundation

/// One channel view's set of inbound-event handlers. Registered with
/// `ChannelsWebSocket.subscribe(_:)`; the socket dispatches every inbound event
/// to every registered subscriber, and each handler self-filters by channelId.
///
/// This replaces the old single-callback model: a main-window channel tab and
/// an embedded collab-project chat are alive at the same time and both need the
/// echoes for their own channel. With one callback slot, whichever view wired
/// up last stole delivery, so the loser's optimistic sends never reconciled and
/// flipped to "failed" after the 8s timeout.
struct ChannelSubscriber {
    var onMessage: ((ChannelMessage) -> Void)?
    var onMessageDeleted: ((_ messageId: String, _ deletedBy: String) -> Void)?
    var onMessageEdited: ((_ messageId: String, _ content: String, _ editedAt: String?) -> Void)?
    var onReactionUpdate: ((_ messageId: String, _ reactions: [ChannelReaction]) -> Void)?
    var onOnlineUsers: (([ChannelOnlineUser]) -> Void)?
    var onUserJoined: ((ChannelOnlineUser) -> Void)?
    var onUserLeft: ((ChannelOnlineUser) -> Void)?
    var onTyping: ((_ userId: String, _ name: String) -> Void)?
    var onError: ((String) -> Void)?
}

@MainActor
final class ChannelsWebSocket: NSObject {
    static let shared = ChannelsWebSocket()

    private var task: URLSessionWebSocketTask?
    private var session: URLSession?
    private var isConnecting = false
    private(set) var isConnected = false
    private var currentRoom: String?
    /// Channels the client wants to be a member of. Replayed to the server as
    /// `join_room` frames on every WS handshake (cold start + reconnect), so
    /// server-side `room_members` always matches this set. Do NOT use this as
    /// a "we've told the server" flag — that breaks when the frame is sent
    /// before the WS is connected.
    private var subscribedRooms: Set<String> = []
    private var roomNames: [String: String] = [:]
    private var pingTask: Task<Void, Never>?
    private var reconnectTask: Task<Void, Never>?
    private var reconnectDelay: Double = 3.0
    /// Held while the socket is connected so macOS App Nap doesn't suspend the
    /// receive loop + ping timer when all windows are minimized — which
    /// otherwise silently stops message delivery (and thus notifications) until
    /// the app is reactivated. `.userInitiatedAllowingIdleSystemSleep` keeps us
    /// un-napped while awake but still lets the Mac sleep when idle.
    #if os(macOS)
    private var napAssertion: NSObjectProtocol?
    #endif

    // ── Per-view event subscribers ──────────────────────────────────────────
    // Each live channel view registers a ChannelSubscriber; inbound events fan
    // out to all of them (handlers self-filter by channelId). See the doc on
    // ChannelSubscriber for why this is a registry and not a single callback.
    private var subscribers: [UUID: ChannelSubscriber] = [:]

    func subscribe(_ sub: ChannelSubscriber) -> UUID {
        let token = UUID()
        subscribers[token] = sub
        return token
    }

    func unsubscribe(_ token: UUID) {
        subscribers.removeValue(forKey: token)
    }

    private func dispatch(_ body: (ChannelSubscriber) -> Void) {
        for sub in subscribers.values { body(sub) }
    }

    /// Fires for every inbound message regardless of which view is focused.
    /// Set once by AppState for background notifications; never per-view.
    var onMessageGlobal: ((ChannelMessage) -> Void)?
    var currentRoomName: String?
    // Broadcast (live-audio) events are global app state, owned by AppState.
    var onBroadcastStarted: ((WSBroadcastStarted) -> Void)?
    var onBroadcastEnded: ((WSBroadcastEnded) -> Void)?
    var onBroadcastPublisherChanged: ((WSBroadcastPublisherChanged) -> Void)?
    var onBroadcastTokenGrant: ((WSBroadcastTokenGrant) -> Void)?
    var onCallStarted: ((WSCallStarted) -> Void)?
    var onCallEnded: ((WSCallEnded) -> Void)?
    var onCallInvited: ((WSCallInvited) -> Void)?
    var onCallParticipantsChanged: ((WSCallParticipantsChanged) -> Void)?

    // ── Outbox (durable send queue) ──────────────────────────────────────────
    // Every outbound message is queued here keyed by client_message_id and only
    // removed once the server echoes it back (the echo carries the same cmid).
    // If the socket is down at send time, or drops mid-send, the queue survives
    // — it's persisted to UserDefaults and flushed on every (re)connect — so a
    // message the user "sent" while offline still goes out when we reconnect,
    // even across an app restart. Server-side INSERT is idempotent on
    // (sender_id, client_message_id), so re-sending the same cmid never dupes.
    private struct OutboxItem: Codable {
        let cmid: String
        let channelId: String
        let content: String
        let attachments: [ChannelAttachment]
        let replyToId: String?
        var attempts: Int
    }
    private var outbox: [OutboxItem] = []
    private let outboxKey = "channels_outbox_v1"
    private static let maxSendAttempts = 8

    override private init() {
        super.init()
        loadOutbox()
    }

    private func beginNoNap() {
        // macOS App Nap only. iOS suspends backgrounded sockets by design;
        // background delivery comes from APNs, not a kept-alive socket.
        #if os(macOS)
        guard napAssertion == nil else { return }
        napAssertion = ProcessInfo.processInfo.beginActivity(
            options: [.userInitiatedAllowingIdleSystemSleep],
            reason: "Realtime channel messaging"
        )
        #endif
    }

    private func endNoNap() {
        #if os(macOS)
        if let a = napAssertion {
            ProcessInfo.processInfo.endActivity(a)
            napAssertion = nil
        }
        #endif
    }

    func connect() {
        guard !isConnecting && !isConnected else { return }
        guard let token = APIClient.shared.accessToken else { return }

        // Suffix-anchored derivation (APIClient.wsBase) — the old global
        // "/api" replace corrupted api.* hosts, silently killing realtime.
        guard let url = URL(string: "\(APIClient.shared.wsBase)/ws/channels") else { return }

        isConnecting = true
        var request = URLRequest(url: url)
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        let session = URLSession(configuration: .default, delegate: self, delegateQueue: nil)
        self.session = session
        let task = session.webSocketTask(with: request)
        self.task = task
        task.resume()
        listen()
        startPing()
    }

    func disconnect() {
        endNoNap()
        pingTask?.cancel(); pingTask = nil
        reconnectTask?.cancel(); reconnectTask = nil
        task?.cancel(with: .goingAway, reason: nil)
        task = nil
        session?.invalidateAndCancel()
        session = nil
        isConnected = false
        isConnecting = false
        currentRoom = nil
        subscribedRooms = []
        roomNames = [:]
        // Full teardown (logout). Drop subscribers + the outbox so we never
        // resend a previous user's queued messages after a new login.
        subscribers = [:]
        outbox = []
        persistOutbox()
    }

    func joinRoom(channelId: String, channelName: String? = nil) {
        // Don't leave prior room — keep all subscribed for background notifications.
        currentRoom = channelId
        if let channelName {
            currentRoomName = channelName
            roomNames[channelId] = channelName
        }
        subscribedRooms.insert(channelId)
        if isConnected {
            send(["type": "join_room", "channel_id": channelId])
        } else {
            // didOpenWithProtocol will replay subscribedRooms once the handshake completes.
            connect()
        }
    }

    /// Subscribe to multiple channels for background message delivery.
    /// Call after fetching the channel list so notifications arrive for all channels.
    func joinBackgroundRooms(_ channels: [(id: String, name: String)]) {
        for ch in channels {
            roomNames[ch.id] = ch.name
            subscribedRooms.insert(ch.id)
        }
        if isConnected {
            for ch in channels {
                send(["type": "join_room", "channel_id": ch.id])
            }
        } else {
            // didOpenWithProtocol will replay subscribedRooms once the handshake completes.
            connect()
        }
    }

    func roomName(for channelId: String) -> String? {
        roomNames[channelId]
    }

    func setCurrentRoomName(_ name: String?) {
        currentRoomName = name
    }

    func leaveRoom(channelId: String) {
        if currentRoom == channelId { currentRoom = nil }
        subscribedRooms.remove(channelId)
        if isConnected {
            send(["type": "leave_room", "channel_id": channelId])
        }
    }

    func sendMessage(channelId: String, content: String, attachments: [ChannelAttachment] = [], replyToId: String? = nil, clientMessageId: String? = nil) {
        // Always carry a client_message_id: it's both the optimistic-UI
        // correlation key and the server-side idempotency key for safe resends.
        let cmid = clientMessageId ?? UUID().uuidString
        let item = OutboxItem(
            cmid: cmid, channelId: channelId, content: content,
            attachments: attachments, replyToId: replyToId, attempts: 0,
        )
        enqueueOutbox(item)
        attemptSend(cmid: cmid)
    }

    // ── Outbox plumbing ──────────────────────────────────────────────────────

    private func enqueueOutbox(_ item: OutboxItem) {
        if let idx = outbox.firstIndex(where: { $0.cmid == item.cmid }) {
            outbox[idx] = item
        } else {
            outbox.append(item)
        }
        persistOutbox()
    }

    /// Transmit a single queued message. No-op (leaves it queued) if the socket
    /// isn't up — connect() will flush on open. Drops the item after too many
    /// attempts so a permanently-rejected message can't loop forever.
    private func attemptSend(cmid: String) {
        guard let idx = outbox.firstIndex(where: { $0.cmid == cmid }) else { return }
        guard isConnected, let task else {
            connect()   // didOpenWithProtocol flushes the whole outbox
            return
        }
        if outbox[idx].attempts >= Self.maxSendAttempts {
            outbox.remove(at: idx)
            persistOutbox()
            return
        }
        outbox[idx].attempts += 1
        persistOutbox()
        let item = outbox[idx]
        var payload: [String: Any] = [
            "type": "message",
            "channel_id": item.channelId,
            "content": item.content,
            "client_message_id": item.cmid,
        ]
        if let replyToId = item.replyToId { payload["reply_to_id"] = replyToId }
        if !item.attachments.isEmpty {
            payload["attachments"] = item.attachments.map { att in
                [
                    "url": att.url,
                    "filename": att.filename,
                    "content_type": att.contentType,
                    "size": att.size,
                ]
            }
        }
        guard let data = try? JSONSerialization.data(withJSONObject: payload),
              let str = String(data: data, encoding: .utf8) else { return }
        task.send(.string(str)) { [weak self] error in
            if error != nil {
                // Stays in the outbox; reconnect's flush retries it.
                Task { @MainActor in self?.scheduleReconnect() }
            }
        }
    }

    /// Re-send everything queued. Called on every (re)connect once the handshake
    /// is up. Ensures each queued channel is joined first so the server echoes
    /// our message back to us — the echo is what reconciles the optimistic row.
    private func flushOutbox() {
        guard isConnected, !outbox.isEmpty else { return }
        for channelId in Set(outbox.map { $0.channelId }) {
            subscribedRooms.insert(channelId)
            send(["type": "join_room", "channel_id": channelId])
        }
        for item in outbox { attemptSend(cmid: item.cmid) }
    }

    /// Remove a message from the outbox once the server confirms it (the echo
    /// carries the original client_message_id).
    private func confirmSent(cmid: String?) {
        guard let cmid, !cmid.isEmpty else { return }
        if let idx = outbox.firstIndex(where: { $0.cmid == cmid }) {
            outbox.remove(at: idx)
            persistOutbox()
        }
    }

    private func persistOutbox() {
        if let data = try? JSONEncoder().encode(outbox) {
            UserDefaults.standard.set(data, forKey: outboxKey)
        }
    }

    private func loadOutbox() {
        guard let data = UserDefaults.standard.data(forKey: outboxKey),
              let items = try? JSONDecoder().decode([OutboxItem].self, from: data) else { return }
        outbox = items
    }

    func sendTyping(channelId: String) {
        send(["type": "typing", "channel_id": channelId])
    }

    private func send(_ payload: [String: Any]) {
        guard let task else { return }
        guard let data = try? JSONSerialization.data(withJSONObject: payload),
              let str = String(data: data, encoding: .utf8) else { return }
        task.send(.string(str)) { [weak self] error in
            if error != nil {
                Task { @MainActor in self?.scheduleReconnect() }
            }
        }
    }

    private func listen() {
        task?.receive { [weak self] result in
            Task { @MainActor in
                guard let self else { return }
                switch result {
                case .failure:
                    self.scheduleReconnect()
                case .success(let message):
                    switch message {
                    case .string(let text):
                        self.handle(text: text)
                    case .data(let data):
                        if let text = String(data: data, encoding: .utf8) {
                            self.handle(text: text)
                        }
                    @unknown default:
                        break
                    }
                    self.listen()
                }
            }
        }
    }

    private func handle(text: String) {
        guard let data = text.data(using: .utf8),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let type = obj["type"] as? String else { return }

        switch type {
        case "pong":
            break
        case "server_ping":
            // Server-initiated keepalive. Echo a lightweight ack so the server's
            // send_text doesn't fail and drop us from active_connections.
            send(["type": "pong"])
        case "message":
            if let msgDict = obj["message"] as? [String: Any],
               let msgData = try? JSONSerialization.data(withJSONObject: msgDict),
               let msg = try? JSONDecoder().decode(ChannelMessage.self, from: msgData) {
                // Server confirmed delivery — drop it from the resend queue.
                confirmSent(cmid: msg.clientMessageId)
                dispatch { $0.onMessage?(msg) }
                onMessageGlobal?(msg)
            }
        case "online_users":
            if let users = obj["users"] as? [[String: Any]] {
                let parsed = users.compactMap { dict -> ChannelOnlineUser? in
                    guard let id = dict["id"] as? String, let name = dict["name"] as? String else { return nil }
                    return ChannelOnlineUser(id: id, name: name, avatarUrl: dict["avatar_url"] as? String)
                }
                dispatch { $0.onOnlineUsers?(parsed) }
            }
        case "user_joined":
            if let user = obj["user"] as? [String: Any],
               let id = user["id"] as? String, let name = user["name"] as? String {
                let u = ChannelOnlineUser(id: id, name: name, avatarUrl: user["avatar_url"] as? String)
                dispatch { $0.onUserJoined?(u) }
            }
        case "user_left":
            if let user = obj["user"] as? [String: Any],
               let id = user["id"] as? String, let name = user["name"] as? String {
                let u = ChannelOnlineUser(id: id, name: name, avatarUrl: user["avatar_url"] as? String)
                dispatch { $0.onUserLeft?(u) }
            }
        case "typing":
            if let user = obj["user"] as? [String: Any],
               let id = user["id"] as? String, let name = user["name"] as? String {
                dispatch { $0.onTyping?(id, name) }
            }
        case "message_deleted":
            if let messageId = obj["message_id"] as? String,
               let deletedBy = obj["deleted_by"] as? String {
                dispatch { $0.onMessageDeleted?(messageId, deletedBy) }
            }
        case "message_edited":
            if let messageId = obj["message_id"] as? String,
               let content = obj["content"] as? String {
                let editedAt = obj["edited_at"] as? String
                dispatch { $0.onMessageEdited?(messageId, content, editedAt) }
            }
        case "reaction_update":
            if let messageId = obj["message_id"] as? String,
               let reactionsArr = obj["reactions"] as? [[String: Any]],
               let reactionsData = try? JSONSerialization.data(withJSONObject: reactionsArr),
               let reactions = try? JSONDecoder().decode([ChannelReaction].self, from: reactionsData) {
                dispatch { $0.onReactionUpdate?(messageId, reactions) }
            }
        case "broadcast.started":
            if let channelId = obj["channel_id"] as? String,
               let broadcastId = obj["broadcast_id"] as? String,
               let startedBy = obj["started_by"] as? String,
               let startedAt = obj["started_at"] as? String {
                let event = WSBroadcastStarted(
                    channelId: channelId,
                    broadcastId: broadcastId,
                    startedBy: startedBy,
                    startedAt: startedAt,
                    title: obj["title"] as? String
                )
                onBroadcastStarted?(event)
            }
        case "broadcast.ended":
            if let channelId = obj["channel_id"] as? String,
               let broadcastId = obj["broadcast_id"] as? String {
                onBroadcastEnded?(WSBroadcastEnded(channelId: channelId, broadcastId: broadcastId))
            }
        case "broadcast.publisher_changed":
            if let channelId = obj["channel_id"] as? String,
               let userId = obj["user_id"] as? String,
               let canPublish = obj["can_publish"] as? Bool {
                onBroadcastPublisherChanged?(WSBroadcastPublisherChanged(
                    channelId: channelId, userId: userId, canPublish: canPublish
                ))
            }
        case "broadcast.token_grant":
            if let channelId = obj["channel_id"] as? String,
               let token = obj["token"] as? String,
               let liveKitUrl = obj["livekit_url"] as? String {
                let canPublish = obj["can_publish"] as? Bool ?? false
                onBroadcastTokenGrant?(WSBroadcastTokenGrant(
                    channelId: channelId, token: token,
                    liveKitUrl: liveKitUrl, canPublish: canPublish
                ))
            }
        case "call.started":
            if let channelId = obj["channel_id"] as? String,
               let callId = obj["call_id"] as? String,
               let startedBy = obj["started_by"] as? String,
               let startedAt = obj["started_at"] as? String,
               let mode = obj["mode"] as? String {
                onCallStarted?(WSCallStarted(
                    channelId: channelId, callId: callId,
                    startedBy: startedBy, startedAt: startedAt, mode: mode
                ))
            }
        case "call.ended":
            if let channelId = obj["channel_id"] as? String,
               let callId = obj["call_id"] as? String {
                onCallEnded?(WSCallEnded(channelId: channelId, callId: callId))
            }
        case "call.invited":
            if let channelId = obj["channel_id"] as? String,
               let callId = obj["call_id"] as? String,
               let invitedBy = obj["invited_by"] as? String {
                onCallInvited?(WSCallInvited(channelId: channelId, callId: callId, invitedBy: invitedBy))
            }
        case "call.participants_changed":
            if let channelId = obj["channel_id"] as? String,
               let callId = obj["call_id"] as? String,
               let participantIds = obj["participant_ids"] as? [String] {
                onCallParticipantsChanged?(WSCallParticipantsChanged(
                    channelId: channelId, callId: callId, participantIds: participantIds
                ))
            }
        case "notification":
            if let n = obj["notification"] as? [String: Any] {
                NotificationCenter.default.post(
                    name: .mwNewNotification,
                    object: nil,
                    userInfo: ["notification": n]
                )
            }
        case "error":
            if let msg = obj["message"] as? String { dispatch { $0.onError?(msg) } }
        default:
            break
        }
    }

    private func startPing() {
        pingTask?.cancel()
        pingTask = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(30))
                guard let self else { return }
                await MainActor.run {
                    self.send(["type": "ping"])
                }
            }
        }
    }

    private func scheduleReconnect() {
        guard reconnectTask == nil else { return }
        print("[ChannelsWS] schedule reconnect — delay=\(reconnectDelay)s")
        isConnected = false
        isConnecting = false
        pingTask?.cancel(); pingTask = nil
        task?.cancel(with: .goingAway, reason: nil)
        task = nil
        let delay = reconnectDelay
        reconnectDelay = min(reconnectDelay * 2, 60)
        // subscribedRooms is intentionally kept — didOpenWithProtocol replays
        // every entry as a join_room frame once the new handshake completes.
        reconnectTask = Task { [weak self] in
            try? await Task.sleep(for: .seconds(delay))
            guard let self else { return }
            // Refresh access token before reconnect. A stale token causes
            // a silent 4001 close that traps us in an exponential-backoff
            // loop until something else (a REST 401) refreshes the token —
            // which is why "click out + click back in" recovers the chat
            // stream. Matches the ProjectWebSocket fix in b653ddd.
            let refreshed = await AuthService.shared.refreshIfNeeded()
            print("[ChannelsWS] reconnect token refresh=\(refreshed)")
            await MainActor.run {
                self.reconnectTask = nil
                self.connect()
            }
        }
    }
}

extension Notification.Name {
    /// Posted when the server pushes a new bell notification over the channels WS.
    /// userInfo["notification"] holds the raw notification dict (id/type/title/body/link/metadata/created_at).
    static let mwNewNotification = Notification.Name("mw-new-notification")
    /// Posted by AppState after a push lands; the popover refetches when visible.
    static let mwNotificationsRefresh = Notification.Name("mw-notifications-refresh")
    /// Posted by AppDelegate when the user clicks a macOS notification banner.
    /// userInfo carries "link" (String) and/or "metadata" ([String: String])
    /// as stashed on the UNNotification by ChannelNotificationManager.
    static let mwNotificationBannerTapped = Notification.Name("mw-notification-banner-tapped")
}

extension ChannelsWebSocket: URLSessionWebSocketDelegate {
    nonisolated func urlSession(_ session: URLSession, webSocketTask: URLSessionWebSocketTask, didOpenWithProtocol protocol: String?) {
        Task { @MainActor in
            print("[ChannelsWS] connected — replaying \(self.subscribedRooms.count) join_room frames")
            self.isConnected = true
            self.isConnecting = false
            self.reconnectDelay = 3.0
            self.beginNoNap()
            // Replay every channel the client wants to be in. Server reconciles
            // room_members against this set — without this, joins sent before
            // the handshake completed (cold start, scheduleReconnect) are lost
            // and the user gets no broadcasts.
            for roomId in self.subscribedRooms {
                self.send(["type": "join_room", "channel_id": roomId])
            }
            // Re-send anything queued while we were down (incl. messages
            // persisted to the outbox across an app restart). Joins above run
            // first so the server echoes each resent message back to us.
            self.flushOutbox()
        }
    }

    nonisolated func urlSession(_ session: URLSession, webSocketTask: URLSessionWebSocketTask, didCloseWith closeCode: URLSessionWebSocketTask.CloseCode, reason: Data?) {
        let codeRaw = closeCode.rawValue
        Task { @MainActor in
            print("[ChannelsWS] WS closed code=\(codeRaw)")
            self.endNoNap()
            self.scheduleReconnect()
        }
    }
}
