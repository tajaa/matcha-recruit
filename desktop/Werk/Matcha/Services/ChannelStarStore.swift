import Foundation
import Combine

/// Per-user starred channels — picks which channels post macOS push
/// notifications and float to the top of the sidebar. Persists in
/// UserDefaults under a per-user key so signing in as a different user
/// on the same Mac doesn't surface the previous user's stars.
///
/// Star is purely client-side for v1 — no backend table, no cross-device
/// sync. Trade-off: simple to ship; users on multiple Macs will need to
/// re-star. v2 can move to a `channel_members.starred_at` column.
@MainActor
@Observable
final class ChannelStarStore {
    static let shared = ChannelStarStore()

    /// Bumped on every change so SwiftUI views observing the store
    /// re-render. The underlying Set is private to keep mutation routed
    /// through the public API (so persistence stays in sync).
    private(set) var generation: Int = 0

    private var starred: Set<String> = []
    private var userId: String?

    private init() {}

    private func key(for userId: String) -> String { "mw-starred-channels:\(userId)" }

    /// Bind the store to the currently logged-in user. Call from
    /// AppState.didLogin / didLogout. Reads persisted set or clears on
    /// logout. Idempotent on the same userId.
    func bind(userId: String?) {
        guard self.userId != userId else { return }
        self.userId = userId
        if let userId, let raw = UserDefaults.standard.array(forKey: key(for: userId)) as? [String] {
            starred = Set(raw)
        } else {
            starred = []
        }
        generation &+= 1
    }

    func isStarred(_ channelId: String) -> Bool {
        starred.contains(channelId)
    }

    func toggle(_ channelId: String) {
        if starred.contains(channelId) {
            starred.remove(channelId)
        } else {
            starred.insert(channelId)
        }
        persist()
        generation &+= 1
    }

    func setStarred(_ channelId: String, _ value: Bool) {
        let changed: Bool
        if value {
            changed = starred.insert(channelId).inserted
        } else {
            changed = starred.remove(channelId) != nil
        }
        if changed {
            persist()
            generation &+= 1
        }
    }

    private func persist() {
        guard let userId else { return }
        UserDefaults.standard.set(Array(starred), forKey: key(for: userId))
    }
}

/// Per-user starred journals — same client-side UserDefaults model as
/// `ChannelStarStore` (no backend column, no migration). Surfaces starred
/// journals in the sidebar Starred pins strip and floats them in the
/// Journals hub. v2 could move to a `mw_journals.starred_at` column.
@MainActor
@Observable
final class JournalStarStore {
    static let shared = JournalStarStore()

    private(set) var generation: Int = 0
    private var starred: Set<String> = []
    private var userId: String?

    private init() {}

    private func key(for userId: String) -> String { "mw-starred-journals:\(userId)" }

    func bind(userId: String?) {
        guard self.userId != userId else { return }
        self.userId = userId
        if let userId, let raw = UserDefaults.standard.array(forKey: key(for: userId)) as? [String] {
            starred = Set(raw)
        } else {
            starred = []
        }
        generation &+= 1
    }

    func isStarred(_ journalId: String) -> Bool { starred.contains(journalId) }

    func toggle(_ journalId: String) {
        if starred.contains(journalId) {
            starred.remove(journalId)
        } else {
            starred.insert(journalId)
        }
        persist()
        generation &+= 1
    }

    private func persist() {
        guard let userId else { return }
        UserDefaults.standard.set(Array(starred), forKey: key(for: userId))
    }
}
