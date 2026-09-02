import Foundation

/// Retains detail view-models across tab switches so re-opening a previously
/// visited project / thread / channel repaints instantly from already-loaded
/// data (the detail view then only background-revalidates) instead of cold-
/// fetching from scratch.
///
/// Crucially this holds **view-models only**, never views. The detail views
/// themselves still tear down and rebuild on every tab switch (PrimaryDetailPane
/// is an if/else chain) — so this does NOT keep heavy chat trees mounted, which
/// the DetailPanes perf note warns against. Only the lightweight @Observable VM
/// (and its already-fetched data) survives.
///
/// A small LRU cap bounds memory: cycling through more than `cap` entities
/// evicts the least-recently-used VM, which simply cold-loads on its next visit.
@MainActor
final class WorkDetailVMStore {
    static let shared = WorkDetailVMStore()
    private init() {}

    /// Least-recently-used entities to keep warm, **per kind** (see `lru`).
    /// Typical usage ping-pongs between a handful of tabs; 6 of each covers
    /// that without unbounded growth.
    private let cap = 6

    // All detail VMs are Foundation/SwiftUI portable. Views remain responsible
    // for mounting only the surfaces appropriate to their platform.
    private var projectVMs: [String: ProjectDetailViewModel] = [:]
    private var threadVMs: [String: ThreadDetailViewModel] = [:]
    private var channelVMs: [String: ChannelChatViewModel] = [:]
    /// MRU-first keys ("p:<id>" / "t:<id>" / "c:<id>"), tracked **per kind**.
    /// One shared list meant `cap` was spent across projects, threads and
    /// channels together: three projects, two threads and two channels was
    /// enough to evict the first project, and a project VM is by far the most
    /// expensive to rebuild (it drives the cold `/bundle` + skeleton path).
    /// Each kind now gets its own `cap`.
    private var lru: [String: [String]] = [:]

    // MARK: - Vend

    func projectVM(_ id: String) -> ProjectDetailViewModel {
        let key = "p:\(id)"
        if let vm = projectVMs[id] { touch(key); return vm }
        let vm = ProjectDetailViewModel()
        projectVMs[id] = vm
        touch(key)
        return vm
    }

    func threadVM(_ id: String) -> ThreadDetailViewModel {
        let key = "t:\(id)"
        if let vm = threadVMs[id] { touch(key); return vm }
        let vm = ThreadDetailViewModel()
        threadVMs[id] = vm
        touch(key)
        return vm
    }

    func channelVM(_ id: String) -> ChannelChatViewModel {
        let key = "c:\(id)"
        if let vm = channelVMs[id] { touch(key); return vm }
        let vm = ChannelChatViewModel()
        channelVMs[id] = vm
        touch(key)
        return vm
    }

    // MARK: - Invalidation

    /// Drop a cached VM so its next visit rebuilds fresh. Call alongside the
    /// MatchaWorkService per-entity cache invalidations and on delete/complete.
    /// Pass the prefixed key, e.g. `evict("p:\(projectId)")`.
    func evict(_ key: String) {
        remove(key)
        if let kind = Self.kind(of: key) {
            lru[kind]?.removeAll { $0 == key }
        }
    }

    func evictProject(_ id: String) { evict("p:\(id)") }
    func evictThread(_ id: String) { evict("t:\(id)") }
    func evictChannel(_ id: String) { evict("c:\(id)") }

    /// Drop every cached VM. Must be called on logout: these VMs retain the
    /// previous user's loaded data (keyed only by entity id), so without this a
    /// notification deep-link — or any re-open of the same id — after a user
    /// switch on a shared Mac would repaint user A's data for user B before any
    /// (server-rejected) revalidation. The MatchaWorkService/JournalService
    /// data caches are already scope-cleared on logout; this closes the VM tier.
    func clearAll() {
        projectVMs.removeAll()
        threadVMs.removeAll()
        channelVMs.removeAll()
        lru.removeAll()
    }

    // MARK: - LRU bookkeeping

    private func touch(_ key: String) {
        guard let kind = Self.kind(of: key) else { return }
        var keys = lru[kind] ?? []
        keys.removeAll { $0 == key }
        keys.insert(key, at: 0)
        while keys.count > cap, let evicted = keys.popLast() {
            remove(evicted)
        }
        lru[kind] = keys
    }

    /// The kind prefix of a namespaced key ("p" / "t" / "c"), or nil if the key
    /// is malformed.
    private static func kind(of key: String) -> String? {
        guard let sep = key.firstIndex(of: ":") else { return nil }
        return String(key[..<sep])
    }

    /// Remove the VM behind a key from whichever dictionary owns it.
    private func remove(_ key: String) {
        guard let sep = key.firstIndex(of: ":") else { return }
        let kind = key[..<sep]
        let id = String(key[key.index(after: sep)...])
        switch kind {
        case "p": projectVMs[id] = nil
        case "t": threadVMs[id] = nil
        case "c": channelVMs[id] = nil
        default: break
        }
    }
}
