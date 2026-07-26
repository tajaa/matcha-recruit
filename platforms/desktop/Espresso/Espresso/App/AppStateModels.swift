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
