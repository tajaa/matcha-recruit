import SwiftUI

enum CollabRightPanel: String, CaseIterable, Identifiable {
    case chat, kanban, files, media, elements, sections, threads, overview
    var id: String { rawValue }
    var label: String {
        switch self {
        case .chat: return "Chat"
        case .kanban: return "Kanban"
        case .files: return "Files"
        case .media: return "Media"
        case .elements: return "Elements"
        case .sections: return "Sections"
        case .threads: return "Threads"
        case .overview: return "Overview"
        }
    }
    var icon: String {
        switch self {
        case .chat: return "bubble.left.and.bubble.right"
        case .kanban: return "rectangle.split.3x1"
        case .files: return "doc.on.doc"
        case .media: return "photo.stack"
        case .elements: return "square.stack.3d.up"
        case .sections: return "list.bullet.rectangle"
        case .threads: return "bubble.left.and.text.bubble.right"
        case .overview: return "rectangle.grid.2x2"
        }
    }
    /// Cmd-N shortcut character; index in `allCases` + 1.
    var shortcutKey: KeyEquivalent {
        switch self {
        case .chat: return "1"
        case .kanban: return "2"
        case .files: return "3"
        case .media: return "4"
        case .elements: return "5"
        case .sections: return "6"
        case .overview: return "7"
        case .threads: return "8"
        }
    }
}

enum StandardProjectMode: String, CaseIterable, Identifiable {
    case edit, preview
    var id: String { rawValue }
    var label: String {
        switch self {
        case .edit: return "Edit"
        case .preview: return "Preview"
        }
    }
}
