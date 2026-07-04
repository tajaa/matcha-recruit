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
    // Live section co-editing (soft-lock + live content).
    var onSectionLocked: ((_ sectionId: String, _ userId: String, _ userName: String) -> Void)?
    var onSectionUnlocked: ((_ sectionId: String) -> Void)?
    var onSectionLockDenied: ((_ sectionId: String, _ holderId: String?, _ holderName: String?) -> Void)?
    var onSectionContent: ((_ sectionId: String, _ title: String?, _ content: String) -> Void)?
    /// task.created / task.updated / task.deleted fan-out. Unlike the other
    /// callbacks (single-closure, owned by whichever view is frontmost), task
    /// events use a per-owner REGISTRY keyed by the event's project_id: the
    /// old single closures were silently stolen by the last view to attach
    /// (embedded panes, cached VMs, aux windows) and nuked wholesale by
    /// `clearCallbacks()` on ANY project view teardown — SwiftUI's
    /// disappear-after-appear ordering meant switching projects could clear
    /// the new board's just-attached callbacks, killing realtime until the
    /// next reattach. Every registered VM whose projectId matches the event
    /// gets the payload; entries auto-prune when their owner deallocates.
    struct TaskEventHandlers {
        /// Payload dict is the raw task row plus `actor_id` for self-echo
        /// suppression.
        let onCreated: ([String: Any]) -> Void
        let onUpdated: ([String: Any]) -> Void
        /// task.deleted payload — only `{"id": ..., "actor_id": ...}` shape.
        let onDeleted: (_ taskId: String, _ actorId: String?) -> Void
    }

    private struct TaskHandlerEntry {
        weak var owner: AnyObject?
        let projectId: String
        let handlers: TaskEventHandlers
    }

    private var taskHandlers: [ObjectIdentifier: TaskHandlerEntry] = [:]

    /// Register (or replace) the task-event handlers owned by `owner` for one
    /// project. Idempotent per owner — re-attaching on view re-task just
    /// replaces the entry.
    func registerTaskHandlers(owner: AnyObject, projectId: String, handlers: TaskEventHandlers) {
        taskHandlers[ObjectIdentifier(owner)] = TaskHandlerEntry(
            owner: owner, projectId: projectId, handlers: handlers,
        )
    }

    func unregisterTaskHandlers(owner: AnyObject) {
        taskHandlers.removeValue(forKey: ObjectIdentifier(owner))
    }

    /// Fan a task event out to every live registered owner for that project;
    /// prunes entries whose owner has deallocated along the way.
    private func dispatchTaskEvent(projectId: String?, _ call: (TaskEventHandlers) -> Void) {
        for (key, entry) in taskHandlers {
            guard entry.owner != nil else {
                taskHandlers.removeValue(forKey: key)
                continue
            }
            if projectId == nil || entry.projectId == projectId {
                call(entry.handlers)
            }
        }
    }

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
        guard !isConnecting && !isConnected else {
            print("[ProjectWS] connect skipped — isConnecting=\(isConnecting) isConnected=\(isConnected)")
            return
        }
        guard let token = APIClient.shared.accessToken else {
            print("[ProjectWS] connect skipped — no access token")
            return
        }
        let base = APIClient.shared.baseURL
        let wsBase = base
            .replacingOccurrences(of: "http://", with: "ws://")
            .replacingOccurrences(of: "https://", with: "wss://")
            .replacingOccurrences(of: "/api", with: "")
        guard let url = URL(string: "\(wsBase)/ws/projects") else {
            print("[ProjectWS] connect skipped — invalid URL base=\(base)")
            return
        }
        print("[ProjectWS] connect initiated → \(wsBase)/ws/projects")
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
        print("[ProjectWS] join_project project=\(projectId) page=\(pageKey)")
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

    /// Claim a section for editing. Server replies with `section_lock_denied`
    /// (to us only) if someone else holds it; otherwise watchers get
    /// `section_locked`. We optimistically assume granted until a deny arrives.
    func sendSectionEditStart(projectId: String, pageKey: String, sectionId: String) {
        send(["type": "section_edit_start", "project_id": projectId, "page_key": pageKey, "section_id": sectionId])
    }

    /// Stream live content to watchers while we hold the lock (throttle on the
    /// caller side). Also refreshes the lock TTL server-side.
    func sendSectionContent(projectId: String, pageKey: String, sectionId: String, title: String?, content: String) {
        var payload: [String: Any] = [
            "type": "section_content",
            "project_id": projectId,
            "page_key": pageKey,
            "section_id": sectionId,
            "content": content,
        ]
        if let title { payload["title"] = title }
        send(payload)
    }

    func sendSectionEditEnd(projectId: String, pageKey: String, sectionId: String) {
        send(["type": "section_edit_end", "project_id": projectId, "page_key": pageKey, "section_id": sectionId])
    }

    /// Force-claim a section lock held by someone else (take-over handoff). The
    /// server reassigns the lock and broadcasts the new holder, demoting the
    /// previous editor to watcher.
    func sendSectionEditTakeover(projectId: String, pageKey: String, sectionId: String) {
        send(["type": "section_edit_takeover", "project_id": projectId, "page_key": pageKey, "section_id": sectionId])
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
        onSectionLocked = nil
        onSectionUnlocked = nil
        onSectionLockDenied = nil
        onSectionContent = nil
        // Task handlers deliberately NOT cleared here: they live in the
        // per-owner registry and survive project-view teardown so cached /
        // background VMs keep receiving realtime board updates. Entries
        // self-prune when their owning VM deallocates.
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

        if type != "pong" && type != "cursor" && type != "caret" {
            // Skip pong/cursor/caret to keep the log readable. Everything
            // else (presence, task.*, error) prints once per event.
            print("[ProjectWS] recv type=\(type)")
        }

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
        case "section_locked":
            if let sectionId = obj["section_id"] as? String,
               let userId = obj["user_id"] as? String {
                onSectionLocked?(sectionId, userId, obj["user_name"] as? String ?? "Someone")
            }
        case "section_unlocked":
            if let sectionId = obj["section_id"] as? String {
                onSectionUnlocked?(sectionId)
            }
        case "section_lock_denied":
            if let sectionId = obj["section_id"] as? String {
                onSectionLockDenied?(sectionId, obj["holder_id"] as? String, obj["holder_name"] as? String)
            }
        case "section_content":
            if let sectionId = obj["section_id"] as? String,
               let content = obj["content"] as? String {
                onSectionContent?(sectionId, obj["title"] as? String, content)
            }
        case "task.created":
            if let task = obj["task"] as? [String: Any] {
                dispatchTaskEvent(projectId: obj["project_id"] as? String) { $0.onCreated(task) }
            }
        case "task.updated":
            if let task = obj["task"] as? [String: Any] {
                dispatchTaskEvent(projectId: obj["project_id"] as? String) { $0.onUpdated(task) }
            }
        case "task.deleted":
            if let task = obj["task"] as? [String: Any],
               let taskId = task["id"] as? String {
                dispatchTaskEvent(projectId: obj["project_id"] as? String) {
                    $0.onDeleted(taskId, task["actor_id"] as? String)
                }
            }
        case "error":
            // Server sent {"type":"error","message":"..."}.
            // join_project gates on membership so a permission error here
            // means we shouldn't retry, just stay disconnected on the page.
            print("[ProjectWS] server error: \(obj["message"] ?? "<no message>")")
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
        print("[ProjectWS] schedule reconnect — delay=\(reconnectDelay)s")
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
            // Refresh the access token before reconnecting so a stale one
            // doesn't cause the server to 4001-close the upgrade and trap
            // us in a backoff loop forever. Shared singleton task in
            // AuthService dedups with any concurrent REST refresh.
            let refreshed = await AuthService.shared.refreshIfNeeded()
            print("[ProjectWS] reconnect token refresh=\(refreshed)")
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
