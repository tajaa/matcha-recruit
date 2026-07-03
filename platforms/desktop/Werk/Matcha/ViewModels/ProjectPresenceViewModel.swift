import SwiftUI

/// Observable presence state for a single project view. Owns the WebSocket
/// callbacks while the ProjectDetailView is on screen and exposes:
///
/// - `members`: who's anywhere in the project (drives the header pill)
/// - `remoteCursors`: latest cursor position per remote user (drives the
///   floating dot+name overlay on the active sub-tab)
/// - `remoteCarets`: latest caret per remote user, keyed by section_id
///   (drives the "X is editing" badge on the section list)
///
/// Throttling is local: cursor sends throttled at 50ms, caret sends at
/// 100ms — same budgets the web client uses, well under the server's
/// 60 msg/sec rate limit.
@MainActor
@Observable
final class ProjectPresenceViewModel {
    private(set) var members: [ProjectWebSocket.PresenceMember] = []
    private(set) var remoteCursors: [String: ProjectWebSocket.CursorPayload] = [:]
    private(set) var remoteCarets: [String: ProjectWebSocket.CaretPayload] = [:]
    /// Sections currently held by *another* editor (section_id → holder). Our
    /// own granted lock never lands here (the server excludes the holder from
    /// the `section_locked` broadcast); a `section_lock_denied` for a section we
    /// tried to open does. Drives read-only + "X is editing".
    private(set) var lockedSections: [String: SectionLockHolder] = [:]
    /// Latest live content streamed by the active editor, for watchers.
    private(set) var liveSections: [String: SectionLiveContent] = [:]

    private var projectId: String?
    private var pageKey: String = "sections"
    private var lastCursorSend: Date = .distantPast
    private var lastCaretSend: Date = .distantPast
    private var lastContentSend: [String: Date] = [:]
    private let cursorMinInterval: TimeInterval = 0.050
    private let caretMinInterval: TimeInterval = 0.100
    private let contentMinInterval: TimeInterval = 0.5

    /// Connect (or reuse existing connection), join the project on the given
    /// sub-tab, and wire callbacks into local state.
    func start(projectId: String, pageKey: String) {
        self.projectId = projectId
        self.pageKey = pageKey
        let ws = ProjectWebSocket.shared
        ws.connect()
        ws.onPresence = { [weak self] members in
            self?.members = members
        }
        ws.onPresenceUpdate = { [weak self] userId, newPage in
            guard let self else { return }
            // Replace the page_key on the matching member; leave the rest as-is.
            self.members = self.members.map { m in
                guard m.id == userId else { return m }
                return ProjectWebSocket.PresenceMember(
                    id: m.id, name: m.name, email: m.email, role: m.role,
                    avatarUrl: m.avatarUrl, pageKey: newPage,
                )
            }
        }
        ws.onUserJoined = { [weak self] member in
            guard let self else { return }
            // Replace if present (rare reconnect race), else append.
            self.members.removeAll { $0.id == member.id }
            self.members.append(member)
        }
        ws.onUserLeft = { [weak self] userId in
            guard let self else { return }
            self.members.removeAll { $0.id == userId }
            self.remoteCursors.removeValue(forKey: userId)
            self.remoteCarets.removeValue(forKey: userId)
        }
        ws.onCursor = { [weak self] payload in
            self?.remoteCursors[payload.userId] = payload
        }
        ws.onCaret = { [weak self] payload in
            self?.remoteCarets[payload.userId] = payload
        }
        ws.onSectionLocked = { [weak self] sectionId, userId, name in
            self?.lockedSections[sectionId] = SectionLockHolder(userId: userId, name: name)
        }
        ws.onSectionUnlocked = { [weak self] sectionId in
            self?.lockedSections.removeValue(forKey: sectionId)
            self?.liveSections.removeValue(forKey: sectionId)
        }
        ws.onSectionLockDenied = { [weak self] sectionId, holderId, holderName in
            self?.lockedSections[sectionId] = SectionLockHolder(
                userId: holderId ?? "", name: holderName ?? "Someone"
            )
        }
        ws.onSectionContent = { [weak self] sectionId, title, content in
            self?.liveSections[sectionId] = SectionLiveContent(title: title, content: content)
        }
        ws.joinProject(projectId: projectId, pageKey: pageKey)
    }

    // MARK: - Live section co-editing

    func startEditing(sectionId: String) {
        guard let projectId else { return }
        ProjectWebSocket.shared.sendSectionEditStart(projectId: projectId, pageKey: pageKey, sectionId: sectionId)
    }

    /// Stream live content while holding the lock. Throttled per section; pass
    /// `force` on the final flush so the last keystroke isn't dropped.
    func sendSectionContent(sectionId: String, title: String?, content: String, force: Bool = false) {
        guard let projectId else { return }
        let now = Date()
        if !force, let last = lastContentSend[sectionId], now.timeIntervalSince(last) < contentMinInterval {
            return
        }
        lastContentSend[sectionId] = now
        ProjectWebSocket.shared.sendSectionContent(
            projectId: projectId, pageKey: pageKey, sectionId: sectionId, title: title, content: content
        )
    }

    func endEditing(sectionId: String) {
        guard let projectId else { return }
        lastContentSend.removeValue(forKey: sectionId)
        ProjectWebSocket.shared.sendSectionEditEnd(projectId: projectId, pageKey: pageKey, sectionId: sectionId)
    }

    /// Wrest the section lock from the current holder (watcher → editor). Clears
    /// our own watcher lock optimistically so the editor opens instantly; the
    /// server reassigns the lock and broadcasts the new holder, which demotes
    /// the previous editor to watcher.
    func takeOver(sectionId: String) {
        guard let projectId else { return }
        lockedSections.removeValue(forKey: sectionId)
        liveSections.removeValue(forKey: sectionId)
        ProjectWebSocket.shared.sendSectionEditTakeover(projectId: projectId, pageKey: pageKey, sectionId: sectionId)
    }

    func setPage(_ pageKey: String) {
        guard let projectId, self.pageKey != pageKey else { return }
        self.pageKey = pageKey
        ProjectWebSocket.shared.changePage(projectId: projectId, pageKey: pageKey)
    }

    func reportCursor(xPct: Double, yPct: Double) {
        guard let projectId else { return }
        let now = Date()
        guard now.timeIntervalSince(lastCursorSend) >= cursorMinInterval else { return }
        lastCursorSend = now
        ProjectWebSocket.shared.sendCursor(
            projectId: projectId, pageKey: pageKey,
            xPct: max(0, min(1, xPct)), yPct: max(0, min(1, yPct)),
        )
    }

    func reportCaret(sectionId: String, anchor: Int, head: Int) {
        guard let projectId else { return }
        let now = Date()
        guard now.timeIntervalSince(lastCaretSend) >= caretMinInterval else { return }
        lastCaretSend = now
        ProjectWebSocket.shared.sendCaret(
            projectId: projectId, pageKey: pageKey,
            sectionId: sectionId, anchor: anchor, head: head,
        )
    }

    func stop() {
        print("[PresenceVM] stop — clearing ProjectWS callbacks")
        let ws = ProjectWebSocket.shared
        if let pid = projectId { ws.leaveProject(projectId: pid) }
        ws.clearCallbacks()
        members = []
        remoteCursors = [:]
        remoteCarets = [:]
        lockedSections = [:]
        liveSections = [:]
        lastContentSend = [:]
        projectId = nil
    }
}

/// Who currently holds a section's edit lock.
struct SectionLockHolder: Equatable {
    let userId: String
    let name: String
}

/// Live content streamed by the active editor, shown to watchers read-only.
struct SectionLiveContent: Equatable {
    let title: String?
    let content: String
}

/// Stable per-user color for cursor + caret rendering. Hash the user id
/// into a fixed palette so the same collaborator gets the same color
/// across sessions and across the app (avatar circle, cursor dot, caret bar).
enum UserColor {
    private static let palette: [Color] = [
        Color(red: 0.92, green: 0.40, blue: 0.40), // red
        Color(red: 0.40, green: 0.74, blue: 0.45), // green
        Color(red: 0.30, green: 0.62, blue: 0.92), // blue
        Color(red: 0.95, green: 0.65, blue: 0.30), // orange
        Color(red: 0.66, green: 0.45, blue: 0.88), // purple
        Color(red: 0.95, green: 0.46, blue: 0.69), // pink
        Color(red: 0.30, green: 0.74, blue: 0.74), // teal
        Color(red: 0.86, green: 0.78, blue: 0.30), // gold
    ]

    static func forUserId(_ id: String) -> Color {
        let hash = id.unicodeScalars.reduce(0) { ($0 &* 31) &+ Int($1.value) }
        return palette[abs(hash) % palette.count]
    }
}
