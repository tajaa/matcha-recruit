import Foundation

/// Per-user order of the sidebar's sections inside each group (WORK,
/// PERSONAL). Persists in UserDefaults under a per-user key so signing in as a
/// different user on the same Mac doesn't surface the previous user's layout.
/// Local-only: no backend, no cross-device sync.
///
/// Everything above the groups is fixed: the Espresso card, Tasks, Home,
/// Find anything and the Pinned list. A section moves only within its group.
@MainActor
@Observable
final class SidebarSectionOrderStore {
    static let shared = SidebarSectionOrderStore()

    /// The sidebar's groups of sections, in the order they show.
    enum Group: String, CaseIterable, Identifiable {
        case work
        case personal

        var id: String { rawValue }

        var title: String {
            switch self {
            case .work: return "WORK"
            case .personal: return "PERSONAL"
            }
        }

        /// The default order of its sections.
        var sections: [Section] { Section.allCases.filter { $0.group == self } }
    }

    /// Stable identifiers for each sidebar section. String values are the
    /// persistence keys: don't rename without a migration. (Espresso, Tasks
    /// and Job search were sections until the sidebar's redesign; a saved
    /// order that still names them just drops them.)
    enum Section: String, CaseIterable, Identifiable {
        case projects
        case channels
        case threads
        case calendar
        case productivity
        case journals
        case email

        var id: String { rawValue }

        var group: Group {
            switch self {
            case .projects, .channels, .threads: return .work
            case .calendar, .productivity, .journals, .email: return .personal
            }
        }

        /// SF Symbol used in the drag preview / context menu.
        var iconName: String {
            switch self {
            case .channels: return "number"
            case .projects: return "square.grid.2x2"
            case .journals: return "book.closed"
            case .productivity: return "checklist"
            case .calendar: return "calendar"
            case .threads:  return "bubble.left.and.bubble.right"
            case .email:    return "envelope"
            }
        }

        /// Human-readable title for the drag preview pill.
        var displayName: String {
            switch self {
            case .channels: return "Channels"
            // `.projects` rawValue stays "projects" — it's the persistence key.
            case .projects: return "Workspaces"
            case .journals: return "Journals"
            case .productivity: return "Productivity"
            case .calendar: return "Calendar"
            case .threads:  return "Threads"
            case .email:    return "Email"
            }
        }
    }

    /// Each group's sections in the person's order. Always every section of
    /// the group exactly once.
    private(set) var orders: [Group: [Section]] = SidebarSectionOrderStore.defaults
    /// Bumped on every change so SwiftUI views observing the store
    /// re-render. Same pattern as ChannelStarStore.
    private(set) var generation: Int = 0

    private var userId: String?

    private init() {}

    static let defaults: [Group: [Section]] = Dictionary(uniqueKeysWithValues: Group.allCases.map { ($0, $0.sections) })

    private static func key(for userId: String) -> String {
        "mw-sidebar-group-order-v1:\(userId)"
    }

    /// The flat order saved before groups existed: read once to carry a
    /// person's arrangement over, never written again.
    private static func legacyKey(for userId: String) -> String {
        "mw-sidebar-section-order:\(userId)"
    }

    func order(_ group: Group) -> [Section] {
        orders[group] ?? group.sections
    }

    /// Bind to the currently logged-in user. Call from AppState.didLogin /
    /// didLogout. Reads the saved order (or the old flat one) or resets.
    func bind(userId: String?) {
        guard self.userId != userId else { return }
        self.userId = userId
        let defaults = UserDefaults.standard
        if let userId, let saved = defaults.dictionary(forKey: Self.key(for: userId)) as? [String: [String]] {
            orders = Self.orders(from: saved)
        } else if let userId, let flat = defaults.array(forKey: Self.legacyKey(for: userId)) as? [String] {
            orders = Self.orders(fromFlat: flat)
            persist()
        } else {
            orders = Self.defaults
        }
        generation &+= 1
    }

    /// Saved per-group orders, each completed with any section it lacks (a
    /// newer section, or one that moved groups) and cleared of strangers.
    static func orders(from saved: [String: [String]]) -> [Group: [Section]] {
        Dictionary(uniqueKeysWithValues: Group.allCases.map { group in
            (group, merged(saved[group.rawValue] ?? [], into: group))
        })
    }

    /// The old flat order split into groups, keeping each group's relative order.
    static func orders(fromFlat flat: [String]) -> [Group: [Section]] {
        Dictionary(uniqueKeysWithValues: Group.allCases.map { ($0, merged(flat, into: $0)) })
    }

    static func merged(_ raw: [String], into group: Group) -> [Section] {
        var out: [Section] = []
        for value in raw {
            if let section = Section(rawValue: value), section.group == group, !out.contains(section) {
                out.append(section)
            }
        }
        for section in group.sections where !out.contains(section) {
            out.append(section)
        }
        return out
    }

    /// Move a section before another in the same group (drag and drop).
    /// Across groups it does nothing.
    func move(_ section: Section, before target: Section) {
        guard section != target, section.group == target.group else { return }
        var list = order(section.group)
        guard let from = list.firstIndex(of: section), var to = list.firstIndex(of: target) else { return }
        list.remove(at: from)
        if from < to { to -= 1 }
        list.insert(section, at: to)
        set(list, for: section.group)
    }

    /// Context-menu helpers — bump the section up or down one slot in its group.
    func moveUp(_ section: Section) {
        var list = order(section.group)
        guard let idx = list.firstIndex(of: section), idx > 0 else { return }
        list.swapAt(idx, idx - 1)
        set(list, for: section.group)
    }

    func moveDown(_ section: Section) {
        var list = order(section.group)
        guard let idx = list.firstIndex(of: section), idx < list.count - 1 else { return }
        list.swapAt(idx, idx + 1)
        set(list, for: section.group)
    }

    /// Restore the default order. Surfaced as a "Reset" option in the
    /// section context menu so a user who scrambles the layout can recover
    /// without quitting the app.
    func resetToDefault() {
        orders = Self.defaults
        persist()
        generation &+= 1
    }

    private func set(_ list: [Section], for group: Group) {
        orders[group] = list
        persist()
        generation &+= 1
    }

    private func persist() {
        guard let userId else { return }
        let saved = Dictionary(uniqueKeysWithValues: orders.map { ($0.key.rawValue, $0.value.map(\.rawValue)) })
        UserDefaults.standard.set(saved, forKey: Self.key(for: userId))
    }
}
