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

/// Per-tab load state for BoardManageViewModel. Pure and synchronous by
/// design — the app has no mock/protocol seam for its services (all hard
/// singletons), so a value type with no async is the only piece of this
/// screen that's actually unit-testable.
struct TabLoadState: Equatable {
    private var phases: [BoardTab: LoadPhase] = [:]

    func phase(_ tab: BoardTab) -> LoadPhase { phases[tab] ?? .idle }
    func isLoading(_ tab: BoardTab) -> Bool { phase(tab) == .loading }
    func hasLoaded(_ tab: BoardTab) -> Bool { phase(tab) == .loaded }
    var isAnyLoading: Bool { phases.values.contains(.loading) }

    /// True if the caller should actually perform the load. `.loading` is
    /// always skipped (that's the reentrancy guard the shared `isLoading`
    /// flag never had); `.loaded` is skipped unless `force`.
    mutating func begin(_ tab: BoardTab, force: Bool = false) -> Bool {
        let current = phase(tab)
        if current == .loading { return false }
        if current == .loaded && !force { return false }
        phases[tab] = .loading
        return true
    }

    mutating func succeed(_ tab: BoardTab) { phases[tab] = .loaded }
    mutating func fail(_ tab: BoardTab) { phases[tab] = .failed }

    /// Cancellation returns to `.idle`, NOT `.failed` — the next `begin(_:)`
    /// on this tab must retry rather than sitting on a stale failure.
    mutating func cancel(_ tab: BoardTab) { phases[tab] = .idle }

    /// Forces the next `begin(_:)` to actually refetch.
    mutating func invalidate(_ tab: BoardTab) { phases[tab] = .idle }
}
