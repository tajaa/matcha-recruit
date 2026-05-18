import Foundation

/// WebSocket client for matcha-work project presence — werk port of
/// `client/src/api/projectSocket.ts`. Same wire protocol as the backend
/// `server/app/matcha/routes/project_ws.py`:
///
/// - Connect with `?token=<jwt>` to `/ws/projects`.
/// - Send `join_project` with `{project_id, page_key}` to enter a project
///   (drives the cross-tab presence pill) AND a sub-tab (drives cursor /
///   caret fan-out, which is page-scoped).
/// - Send `cursor_move` / `caret_move` while in a page; server enforces
///   60 msg/sec per (user, project). Client mirrors the web throttles
///   (cursor 50ms / caret 100ms) at the call site.
/// - Send `page_change` when switching sub-tabs without leaving the project.
/// - Send `leave_project` on view dismiss.
///
/// Auto-reconnects on close with exponential backoff like ChannelsWebSocket.
@MainActor
final class ProjectWebSocket: NSObject {
    static let shared = ProjectWebSocket()

    private var task: URLSessionWebSocketTask?
    private var session: URLSession?
    private var isConnecting = false
    private(set) var isConnected = false
    /// (project_id, page_key) for the page the user is currently on. Reused
    /// on reconnect so the server immediately replays presence to us.
    private var currentProjectId: String?
    private var currentPageKey: String?
    private var pingTask: Task<Void, Never>?
    private var reconnectTask: Task<Void, Never>?
    private var reconnectDelay: Double = 3.0

    /// Full snapshot of who's in the project (across sub-tabs). Replied to
    /// `join_project` and never auto-pushed by the server — `presence_update`
    /// is the only delta after this initial dump.
    var onPresence: (([PresenceMember]) -> Void)?
    /// One member changed sub-tab. The full member list is available via the
    /// next reconnect snapshot; in the meantime we only know the new page.
    var onPresenceUpdate: ((_ userId: String, _ pageKey: String?) -> Void)?
    var onUserJoined: ((PresenceMember) -> Void)?
    var onUserLeft: ((_ userId: String) -> Void)?
    var onCursor: ((CursorPayload) -> Void)?
    var onCaret: ((CaretPayload) -> Void)?
    /// task.created / task.updated server events. Payload dict is the raw
    /// task row plus `actor_id` for self-echo suppression.
    var onTaskCreated: (([String: Any]) -> Void)?
    var onTaskUpdated: (([String: Any]) -> Void)?
    /// task.deleted payload — only `{"id": ..., "actor_id": ...}` shape.
    var onTaskDeleted: ((_ taskId: String, _ actorId: String?) -> Void)?

    struct PresenceMember: Identifiable, Equatable {
        let id: String
        let name: String
        let email: String
        let role: String
        let avatarUrl: String?
        let pageKey: String?
    }

    struct CursorPayload {
        let userId: String
        let xPct: Double
        let yPct: Double
    }

    struct CaretPayload {
        let userId: String
        let sectionId: String
        let anchor: Int
        let head: Int
    }

    override private init() { super.init() }

    func connect() {
        guard !isConnecting && !isConnected else { return }
        guard let token = APIClient.shared.accessToken else { return }
        let base = APIClient.shared.baseURL
        let wsBase = base
            .replacingOccurrences(of: "http://", with: "ws://")
            .replacingOccurrences(of: "https://", with: "wss://")
            .replacingOccurrences(of: "/api", with: "")
        guard let url = URL(string: "\(wsBase)/ws/projects?token=\(token)") else { return }
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
        currentProjectId = nil
        currentPageKey = nil
    }

    /// Enter a project + sub-tab. Server replies with a `presence` snapshot.
    /// Idempotent on the same (project, page) pair — useful when SwiftUI
    /// re-fires .task blocks.
    func joinProject(projectId: String, pageKey: String) {
        currentProjectId = projectId
        currentPageKey = pageKey
        send(["type": "join_project", "project_id": projectId, "page_key": pageKey])
    }

    /// Switch sub-tab without leaving the project. Server keeps us in
    /// project_rooms (so the pill still shows us) but moves us between
    /// page_rooms (so cursor traffic switches with us).
    func changePage(projectId: String, pageKey: String) {
        currentPageKey = pageKey
        send(["type": "page_change", "project_id": projectId, "page_key": pageKey])
    }

    func sendCursor(projectId: String, pageKey: String, xPct: Double, yPct: Double) {
        send([
            "type": "cursor_move",
            "project_id": projectId,
            "page_key": pageKey,
            "x_pct": xPct,
            "y_pct": yPct,
        ])
    }

    func sendCaret(projectId: String, pageKey: String, sectionId: String, anchor: Int, head: Int) {
        send([
            "type": "caret_move",
            "project_id": projectId,
            "page_key": pageKey,
            "section_id": sectionId,
            "anchor": anchor,
            "head": head,
        ])
    }

    func leaveProject(projectId: String) {
        send(["type": "leave_project", "project_id": projectId])
        if currentProjectId == projectId {
            currentProjectId = nil
            currentPageKey = nil
        }
    }

    func clearCallbacks() {
        onPresence = nil
        onPresenceUpdate = nil
        onUserJoined = nil
        onUserLeft = nil
        onCursor = nil
        onCaret = nil
        onTaskCreated = nil
        onTaskUpdated = nil
        onTaskDeleted = nil
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
                    case .string(let text): self.handle(text: text)
                    case .data(let data):
                        if let text = String(data: data, encoding: .utf8) { self.handle(text: text) }
                    @unknown default: break
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
        case "pong": break
        case "presence":
            if let members = obj["members"] as? [[String: Any]] {
                onPresence?(members.compactMap(parseMember))
            }
        case "presence_update":
            if let userId = obj["user_id"] as? String {
                onPresenceUpdate?(userId, obj["page_key"] as? String)
            }
        case "user_joined_project":
            if let userDict = obj["user"] as? [String: Any], let m = parseMember(userDict) {
                onUserJoined?(m)
            }
        case "user_left_project":
            if let userId = obj["user_id"] as? String { onUserLeft?(userId) }
        case "cursor":
            if let userId = obj["user_id"] as? String,
               let x = obj["x_pct"] as? Double,
               let y = obj["y_pct"] as? Double {
                onCursor?(CursorPayload(userId: userId, xPct: x, yPct: y))
            }
        case "caret":
            if let userId = obj["user_id"] as? String,
               let sectionId = obj["section_id"] as? String,
               let anchor = obj["anchor"] as? Int,
               let head = obj["head"] as? Int {
                onCaret?(CaretPayload(userId: userId, sectionId: sectionId, anchor: anchor, head: head))
            }
        case "task.created":
            if let task = obj["task"] as? [String: Any] { onTaskCreated?(task) }
        case "task.updated":
            if let task = obj["task"] as? [String: Any] { onTaskUpdated?(task) }
        case "task.deleted":
            if let task = obj["task"] as? [String: Any],
               let taskId = task["id"] as? String {
                onTaskDeleted?(taskId, task["actor_id"] as? String)
            }
        case "error":
            // Server sent {"type":"error","message":"..."} — fail silently;
            // join_project gates on membership so a permission error here
            // means we shouldn't retry, just stay disconnected on the page.
            break
        default: break
        }
    }

    private func parseMember(_ dict: [String: Any]) -> PresenceMember? {
        guard let id = dict["id"] as? String,
              let name = dict["name"] as? String,
              let email = dict["email"] as? String,
              let role = dict["role"] as? String else { return nil }
        return PresenceMember(
            id: id,
            name: name,
            email: email,
            role: role,
            avatarUrl: dict["avatar_url"] as? String,
            pageKey: dict["page_key"] as? String,
        )
    }

    private func startPing() {
        pingTask?.cancel()
        pingTask = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(30))
                guard let self else { return }
                await MainActor.run { self.send(["type": "ping"]) }
            }
        }
    }

    private func scheduleReconnect() {
        guard reconnectTask == nil else { return }
        isConnected = false
        isConnecting = false
        pingTask?.cancel(); pingTask = nil
        task?.cancel(with: .goingAway, reason: nil)
        task = nil
        let delay = reconnectDelay
        reconnectDelay = min(reconnectDelay * 2, 60)
        let pid = currentProjectId
        let pk = currentPageKey
        reconnectTask = Task { [weak self] in
            try? await Task.sleep(for: .seconds(delay))
            guard let self else { return }
            await MainActor.run {
                self.reconnectTask = nil
                self.connect()
                if let pid, let pk { self.joinProject(projectId: pid, pageKey: pk) }
            }
        }
    }
}

extension ProjectWebSocket: URLSessionWebSocketDelegate {
    nonisolated func urlSession(_ session: URLSession, webSocketTask: URLSessionWebSocketTask, didOpenWithProtocol protocol: String?) {
        Task { @MainActor in
            self.isConnected = true
            self.isConnecting = false
            self.reconnectDelay = 3.0
        }
    }

    nonisolated func urlSession(_ session: URLSession, webSocketTask: URLSessionWebSocketTask, didCloseWith closeCode: URLSessionWebSocketTask.CloseCode, reason: Data?) {
        Task { @MainActor in self.scheduleReconnect() }
    }
}
