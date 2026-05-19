import Foundation

/// Per-user order of the top-level sidebar sections in ContentView.
/// Persists in UserDefaults under a per-user key so signing in as a
/// different user on the same Mac doesn't surface the previous user's
/// layout. Local-only for v1 — no backend, no cross-device sync.
///
/// The four sections — Channels / Projects / Journals / Threads — are
/// always all present; reordering shuffles which one renders first.
/// Default order matches the historical ContentView layout.
@MainActor
@Observable
final class SidebarSectionOrderStore {
    static let shared = SidebarSectionOrderStore()

    /// Stable identifiers for each top-level sidebar section. String values
    /// are the persistence keys — don't rename without a migration.
    enum Section: String, CaseIterable, Identifiable {
        case channels
        case projects
        case journals
        case threads

        var id: String { rawValue }

        /// SF Symbol used in the drag preview / context menu.
        var iconName: String {
            switch self {
            case .channels: return "number"
            case .projects: return "folder"
            case .journals: return "book.closed"
            case .threads:  return "bubble.left.and.bubble.right"
            }
        }

        /// Human-readable title for the drag preview pill.
        var displayName: String {
            switch self {
            case .channels: return "Channels"
            case .projects: return "Projects"
            case .journals: return "Journals"
            case .threads:  return "Threads"
            }
        }
    }

    /// The user's preferred section order. Always contains every Section
    /// case exactly once; missing entries fall back to the default tail.
    private(set) var order: [Section] = Section.allCases
    /// Bumped on every change so SwiftUI views observing the store
    /// re-render. Same pattern as ChannelStarStore.
    private(set) var generation: Int = 0

    private var userId: String?

    private init() {}

    private func key(for userId: String) -> String {
        "mw-sidebar-section-order:\(userId)"
    }

    /// Bind to the currently logged-in user. Call from AppState.didLogin /
    /// didLogout. Reads persisted order or resets to default.
    func bind(userId: String?) {
        guard self.userId != userId else { return }
        self.userId = userId
        if let userId,
           let raw = UserDefaults.standard.array(forKey: key(for: userId)) as? [String] {
            // Map saved strings to enum cases, dropping unknown values.
            // Append any Section cases that weren't in the saved list so
            // future-added sections still render even with stale prefs.
            let saved = raw.compactMap { Section(rawValue: $0) }
            var seen = Set(saved)
            var merged = saved
            for s in Section.allCases where !seen.contains(s) {
                merged.append(s)
                seen.insert(s)
            }
            order = merged
        } else {
            order = Section.allCases
        }
        generation &+= 1
    }

    /// Move the section at `source` to `destination`, mirroring the
    /// signature of `Array.move(fromOffsets:toOffset:)`. Used by drag-
    /// drop callbacks (where destination is the desired final index,
    /// possibly past `source`).
    func move(fromOffsets source: IndexSet, toOffset destination: Int) {
        guard let from = source.first, from < order.count else { return }
        let dest = min(max(0, destination), order.count)
        let item = order[from]
        order.remove(at: from)
        let insertAt = (from < dest) ? dest - 1 : dest
        order.insert(item, at: insertAt)
        persist()
        generation &+= 1
    }

    /// Move a section before another. Used by the .draggable +
    /// .dropDestination flow which works in section-id terms.
    func move(_ section: Section, before target: Section) {
        guard section != target,
              let from = order.firstIndex(of: section),
              var to = order.firstIndex(of: target) else { return }
        order.remove(at: from)
        if from < to { to -= 1 }
        order.insert(section, at: to)
        persist()
        generation &+= 1
    }

    /// Context-menu helpers — bump the section up or down one slot.
    func moveUp(_ section: Section) {
        guard let idx = order.firstIndex(of: section), idx > 0 else { return }
        order.swapAt(idx, idx - 1)
        persist()
        generation &+= 1
    }

    func moveDown(_ section: Section) {
        guard let idx = order.firstIndex(of: section), idx < order.count - 1 else { return }
        order.swapAt(idx, idx + 1)
        persist()
        generation &+= 1
    }

    /// Restore the default order. Surfaced as a "Reset" option in the
    /// section context menu so a user who scrambles the layout can recover
    /// without quitting the app.
    func resetToDefault() {
        order = Section.allCases
        persist()
        generation &+= 1
    }

    private func persist() {
        guard let userId else { return }
        UserDefaults.standard.set(order.map { $0.rawValue }, forKey: key(for: userId))
    }
}
