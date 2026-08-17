import Foundation

/// The five sections of the brand Board tab (Views/Brand/BoardManage/).
enum BoardTab: Int, CaseIterable, Identifiable, Hashable {
    case requests, held, posts, members, team

    var id: Int { rawValue }

    var title: String {
        switch self {
        case .requests: return "Requests"
        case .held: return "Held"
        case .posts: return "Posts"
        case .members: return "Members"
        case .team: return "Team"
        }
    }

    /// SF Symbol for the section's index row. Matches the symbol each section's
    /// own EmptyState uses so the index and the empty screen agree.
    var icon: String {
        switch self {
        case .requests: return "person.badge.clock"
        case .held: return "checkmark.bubble"
        case .posts: return "square.and.pencil"
        case .members: return "person.3"
        case .team: return "checkmark.shield"
        }
    }

    /// One-line "what's in here" for the index row.
    var subtitle: String {
        switch self {
        case .requests: return "People asking to join"
        case .held: return "Replies awaiting review"
        case .posts: return "What you've published"
        case .members: return "Who's on the board"
        case .team: return "Moderators and inbox access"
        }
    }
}

enum LoadPhase: Equatable {
    case idle, loading, loaded, failed
}

typealias TabLoadState = SectionLoadState<BoardTab>
