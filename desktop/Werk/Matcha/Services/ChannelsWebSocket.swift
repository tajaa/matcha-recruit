import Foundation

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

    var onMessage: ((ChannelMessage) -> Void)?
    /// Fires for every inbound message regardless of which view owns `onMessage`.
    /// Set once by AppState for background notifications; never cleared by channel views.
    var onMessageGlobal: ((ChannelMessage) -> Void)?
    var currentRoomName: String?
    var onOnlineUsers: (([ChannelOnlineUser]) -> Void)?
    var onUserJoined: ((ChannelOnlineUser) -> Void)?
    var onUserLeft: ((ChannelOnlineUser) -> Void)?
    var onTyping: ((_ userId: String, _ name: String) -> Void)?
    var onMessageDeleted: ((_ messageId: String, _ deletedBy: String) -> Void)?
    var onError: ((String) -> Void)?
    var onBroadcastStarted: ((WSBroadcastStarted) -> Void)?
    var onBroadcastEnded: ((WSBroadcastEnded) -> Void)?
    var onBroadcastPublisherChanged: ((WSBroadcastPublisherChanged) -> Void)?
    var onBroadcastTokenGrant: ((WSBroadcastTokenGrant) -> Void)?

    override private init() {
        super.init()
    }

    func connect() {
        guard !isConnecting && !isConnected else { return }
        guard let token = APIClient.shared.accessToken else { return }

        let base = APIClient.shared.baseURL
        let wsBase = base
            .replacingOccurrences(of: "http://", with: "ws://")
            .replacingOccurrences(of: "https://", with: "wss://")
            .replacingOccurrences(of: "/api", with: "")
        guard let url = URL(string: "\(wsBase)/ws/channels?token=\(token)") else { return }

        isConnecting = true
        let session = URLSession(configuration: .default, delegate: self, delegateQueue: nil)
        self.session = session
        let task = session.webSocketTask(with: url)
        self.task = task
        task.resume()
        listen()
        startPing()
    }

    func disconnect() {
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

    func clearCallbacks() {
        onMessage = nil
        onOnlineUsers = nil
        onUserJoined = nil
        onUserLeft = nil
        onTyping = nil
        onReactionUpdate = nil
        onError = nil
        // Broadcast handlers are owned by AppState (global). Don't clear here
        // — view teardown shouldn't kill the singleton's broadcast routing.
    }

    /// Clear callbacks only if no other view has joined a different room since
    /// the caller wired them up. Avoids the SwiftUI teardown race where a
    /// disappearing channel view wipes the callbacks just set by the next one.
    func clearCallbacksIfRoomMatches(_ channelId: String) {
        guard currentRoom == nil || currentRoom == channelId else { return }
        clearCallbacks()
    }

    func leaveRoom(channelId: String) {
        if currentRoom == channelId { currentRoom = nil }
        subscribedRooms.remove(channelId)
        if isConnected {
            send(["type": "leave_room", "channel_id": channelId])
        }
    }

    var onReactionUpdate: ((_ messageId: String, _ reactions: [ChannelReaction]) -> Void)?

    func sendMessage(channelId: String, content: String, attachments: [ChannelAttachment] = [], replyToId: String? = nil, clientMessageId: String? = nil) {
        var payload: [String: Any] = [
            "type": "message",
            "channel_id": channelId,
            "content": content,
        ]
        if let replyToId { payload["reply_to_id"] = replyToId }
        if let clientMessageId { payload["client_message_id"] = clientMessageId }
        if !attachments.isEmpty {
            payload["attachments"] = attachments.map { att in
                [
                    "url": att.url,
                    "filename": att.filename,
                    "content_type": att.contentType,
                    "size": att.size,
                ]
            }
        }
        send(payload)
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
                onMessage?(msg)
                onMessageGlobal?(msg)
            }
        case "online_users":
            if let users = obj["users"] as? [[String: Any]] {
                let parsed = users.compactMap { dict -> ChannelOnlineUser? in
                    guard let id = dict["id"] as? String, let name = dict["name"] as? String else { return nil }
                    return ChannelOnlineUser(id: id, name: name, avatarUrl: dict["avatar_url"] as? String)
                }
                onOnlineUsers?(parsed)
            }
        case "user_joined":
            if let user = obj["user"] as? [String: Any],
               let id = user["id"] as? String, let name = user["name"] as? String {
                onUserJoined?(ChannelOnlineUser(id: id, name: name, avatarUrl: user["avatar_url"] as? String))
            }
        case "user_left":
            if let user = obj["user"] as? [String: Any],
               let id = user["id"] as? String, let name = user["name"] as? String {
                onUserLeft?(ChannelOnlineUser(id: id, name: name, avatarUrl: user["avatar_url"] as? String))
            }
        case "typing":
            if let user = obj["user"] as? [String: Any],
               let id = user["id"] as? String, let name = user["name"] as? String {
                onTyping?(id, name)
            }
        case "message_deleted":
            if let messageId = obj["message_id"] as? String,
               let deletedBy = obj["deleted_by"] as? String {
                onMessageDeleted?(messageId, deletedBy)
            }
        case "reaction_update":
            if let messageId = obj["message_id"] as? String,
               let reactionsArr = obj["reactions"] as? [[String: Any]],
               let reactionsData = try? JSONSerialization.data(withJSONObject: reactionsArr),
               let reactions = try? JSONDecoder().decode([ChannelReaction].self, from: reactionsData) {
                onReactionUpdate?(messageId, reactions)
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
        case "notification":
            if let n = obj["notification"] as? [String: Any] {
                NotificationCenter.default.post(
                    name: .mwNewNotification,
                    object: nil,
                    userInfo: ["notification": n]
                )
            }
        case "error":
            if let msg = obj["message"] as? String { onError?(msg) }
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
}

extension ChannelsWebSocket: URLSessionWebSocketDelegate {
    nonisolated func urlSession(_ session: URLSession, webSocketTask: URLSessionWebSocketTask, didOpenWithProtocol protocol: String?) {
        Task { @MainActor in
            print("[ChannelsWS] connected — replaying \(self.subscribedRooms.count) join_room frames")
            self.isConnected = true
            self.isConnecting = false
            self.reconnectDelay = 3.0
            // Replay every channel the client wants to be in. Server reconciles
            // room_members against this set — without this, joins sent before
            // the handshake completed (cold start, scheduleReconnect) are lost
            // and the user gets no broadcasts.
            for roomId in self.subscribedRooms {
                self.send(["type": "join_room", "channel_id": roomId])
            }
        }
    }

    nonisolated func urlSession(_ session: URLSession, webSocketTask: URLSessionWebSocketTask, didCloseWith closeCode: URLSessionWebSocketTask.CloseCode, reason: Data?) {
        let codeRaw = closeCode.rawValue
        Task { @MainActor in
            print("[ChannelsWS] WS closed code=\(codeRaw)")
            self.scheduleReconnect()
        }
    }
}
