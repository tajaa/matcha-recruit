import SwiftUI

/// A kanban ticket referenced into the project chat via "Chat about this
/// ticket". Carries just enough to render the reply-style banner and to weave
/// a compact reference into the outgoing message (so the AI + collaborators
/// have context). Identifiable so SwiftUI can animate the banner in/out.
struct TicketChatRef: Identifiable, Equatable {
    let id: String        // task id
    let title: String
    let column: String    // board_column, for the chip label
}

enum CollabRightPanel: String, CaseIterable, Identifiable {
    case chat, kanban, props, files, media, elements, sections, threads, overview, history
    var id: String { rawValue }
    var label: String {
        switch self {
        case .chat: return "Chat"
        case .kanban: return "Kanban"
        case .props: return "Props"
        case .files: return "Files"
        case .media: return "Media"
        case .elements: return "Elements"
        case .sections: return "Notes"
        case .threads: return "Threads"
        case .overview: return "Overview"
        case .history: return "History"
        }
    }
    var icon: String {
        switch self {
        case .chat: return "bubble.left.and.bubble.right"
        case .kanban: return "rectangle.split.3x1"
        case .props: return "lightbulb"
        case .files: return "doc.on.doc"
        case .media: return "photo.stack"
        case .elements: return "square.stack.3d.up"
        case .sections: return "list.bullet.rectangle"
        case .threads: return "bubble.left.and.text.bubble.right"
        case .overview: return "rectangle.grid.2x2"
        case .history: return "clock.arrow.circlepath"
        }
    }
    /// Cmd-N shortcut character; index in `allCases` + 1.
    var shortcutKey: KeyEquivalent {
        switch self {
        case .chat: return "1"
        case .kanban: return "2"
        case .props: return "3"
        case .files: return "4"
        case .media: return "5"
        case .elements: return "6"
        case .sections: return "7"
        case .overview: return "8"
        case .threads: return "9"
        case .history: return "0"
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
