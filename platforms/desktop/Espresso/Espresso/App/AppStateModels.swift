import Foundation

/// One open workspace tab. Home is permanent + non-closable; up to
/// `AppState.maxPinnedTabs` others (project/channel/thread/journal) can be
/// pinned alongside it. `title` is cached at pin time and refreshed when the
/// underlying view loads, so a rename eventually reflects without a stale id.
struct WorkTab: Codable, Hashable, Identifiable {
    enum Kind: String, Codable { case home, project, channel, thread, journal }
    var kind: Kind
    var entityId: String
    var title: String

    var id: String { kind == .home ? "home" : "\(kind.rawValue):\(entityId)" }
    static let home = WorkTab(kind: .home, entityId: "", title: "Home")

    var icon: String {
        switch kind {
        case .home: return "house"
        // Workspaces are panes of work (chat, board, files), not a place files
        // sit — a folder glyph reads as the Files tab inside one.
        case .project: return "square.grid.2x2"
        case .channel: return "number"
        case .thread: return "bubble.left"
        case .journal: return "book.closed"
        }
    }
}

/// What a secondary (aux) window is pinned to. Codable + Hashable so it can be
/// passed as a WindowGroup presentation value via `openWindow(id:value:)`.
/// Each detail view it maps to is rendered with `isEmbedded: true` so it never
/// writes the shared nav/tab context of the main window.
enum AuxWindowTarget: Codable, Hashable {
    case project(String)
    case channel(String)
    case thread(String)
    case journal(String)
    /// A project file — previewable in a split pane / aux window like any
    /// surface. Carries a snapshot ref (not just an id) so panes don't have to
    /// refetch project file lists to resolve it.
    case file(MWFileRef)
    // Whole surfaces, for keeping one beside whatever is open (a thread next
    // to the calendar). In a side pane each renders its pane layout
    // (`WorkPane.isSide`): the hubs with one canvas (calendar, kanban, email,
    // Espresso) adapt to the narrower width, and the list hubs (threads,
    // channels, journals, workspaces) show a list that opens items in place.
    case calendar
    case journals
    case kanban
    case assistant
    case channels
    case threads
    case email
    case workspaces
}

extension AuxWindowTarget {
    /// The surfaces offered in a side pane's dock and the View menu, in order.
    /// `.assistant` is dropped where the workspace has no Espresso assistant.
    static func dock(assistantEnabled: Bool) -> [AuxWindowTarget] {
        let all: [AuxWindowTarget] = [.calendar, .journals, .kanban, .assistant, .channels, .threads, .email, .workspaces]
        return assistantEnabled ? all : all.filter { $0 != .assistant }
    }

    /// The surface an item belongs to, so the dock can show where a pane is
    /// (a journal open in a pane lights up Journals). nil for a file.
    var surface: AuxWindowTarget? {
        switch self {
        case .thread: return .threads
        case .channel: return .channels
        case .journal: return .journals
        case .project: return .workspaces
        case .file: return nil
        default: return self
        }
    }

    /// Whether this is a whole surface rather than one item in it.
    var isSurface: Bool { surface == self }

    /// Whether ⌘\ may bring it back later. A file carries a signed storage
    /// URL, which is not something to write to preferences.
    var isRememberable: Bool {
        if case .file = self { return false }
        return true
    }

    var surfaceName: String {
        switch self {
        case .calendar: return "Calendar"
        case .journals, .journal: return "Journals"
        case .kanban: return "Kanban"
        case .assistant: return "Espresso"
        case .channels, .channel: return "Channels"
        case .threads, .thread: return "Threads"
        case .email: return "Email"
        case .workspaces, .project: return "Workspaces"
        case .file(let ref): return ref.filename
        }
    }

    var icon: String {
        switch self {
        case .calendar: return "calendar"
        case .journals, .journal: return "book.closed"
        case .kanban: return "checklist"
        case .assistant: return "sparkles"
        case .channels, .channel: return "number"
        case .threads, .thread: return "bubble.left.and.bubble.right"
        case .email: return "envelope"
        case .workspaces, .project: return "square.grid.2x2"
        case .file(let ref): return ref.asProjectFile.isImage ? "photo" : "doc"
        }
    }
}

/// Lightweight Codable snapshot of a project file, used wherever a file needs
/// to outlive its source list: split-pane targets (`AuxWindowTarget.file`) and
/// sidebar Starred pins (`FileStarStore`).
struct MWFileRef: Codable, Hashable {
    let id: String
    let projectId: String?
    let filename: String
    let storageUrl: String
    let contentType: String?
    let fileSize: Int

    init(file: MWProjectFile) {
        id = file.id
        projectId = file.projectId
        filename = file.filename
        storageUrl = file.storageUrl
        contentType = file.contentType
        fileSize = file.fileSize
    }

    /// Adapt back to the shared preview model (`AttachmentPreviewSheet` /
    /// `AttachmentPreviewContent` take an MWProjectFile).
    var asProjectFile: MWProjectFile {
        MWProjectFile(
            id: id, projectId: projectId, taskId: nil, uploadedBy: nil,
            filename: filename, storageUrl: storageUrl,
            contentType: contentType, fileSize: fileSize, createdAt: nil
        )
    }
}
