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

    /// Last-recently-used entities to keep warm. Typical usage ping-pongs
    /// between a handful of tabs; 6 covers that without unbounded growth.
    private let cap = 6

    private var projectVMs: [String: ProjectDetailViewModel] = [:]
    private var threadVMs: [String: ThreadDetailViewModel] = [:]
    private var channelVMs: [String: ChannelChatViewModel] = [:]
    /// MRU-first list of keys ("p:<id>" / "t:<id>" / "c:<id>").
    private var lru: [String] = []

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
        lru.removeAll { $0 == key }
    }

    func evictProject(_ id: String) { evict("p:\(id)") }
    func evictThread(_ id: String) { evict("t:\(id)") }
    func evictChannel(_ id: String) { evict("c:\(id)") }

    // MARK: - LRU bookkeeping

    private func touch(_ key: String) {
        lru.removeAll { $0 == key }
        lru.insert(key, at: 0)
        while lru.count > cap, let evicted = lru.popLast() {
            remove(evicted)
        }
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
