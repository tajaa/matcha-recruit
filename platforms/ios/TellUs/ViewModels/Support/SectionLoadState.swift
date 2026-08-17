import Foundation

/// Per-section load state shared by the board and friends hubs.
struct SectionLoadState<Tab: Hashable>: Equatable {
    private var phases: [Tab: LoadPhase] = [:]

    func phase(_ tab: Tab) -> LoadPhase { phases[tab] ?? .idle }
    func isLoading(_ tab: Tab) -> Bool { phase(tab) == .loading }
    func hasLoaded(_ tab: Tab) -> Bool { phase(tab) == .loaded }
    var isAnyLoading: Bool { phases.values.contains(.loading) }

    mutating func begin(_ tab: Tab, force: Bool = false) -> Bool {
        let current = phase(tab)
        if current == .loading { return false }
        if current == .loaded && !force { return false }
        phases[tab] = .loading
        return true
    }

    mutating func succeed(_ tab: Tab) { phases[tab] = .loaded }
    mutating func fail(_ tab: Tab) { phases[tab] = .failed }
    mutating func cancel(_ tab: Tab) { phases[tab] = .idle }
    mutating func invalidate(_ tab: Tab) { phases[tab] = .idle }
}
