import Foundation

/// TTL cache entry used by `MatchaWorkService` and its sub-services.
/// Internal so sub-services in the same module can construct entries
/// against their own cache dicts without depending on the facade type.
struct MWCacheEntry<Value> {
    let value: Value
    let expiresAt: Date

    var isValid: Bool {
        expiresAt > Date()
    }
}

/// Lock-guarded string-keyed TTL cache. `MatchaWorkService` is a shared,
/// non-isolated singleton whose cache dictionaries were previously bare `var`s
/// mutated from concurrent background `async` methods — concurrent mutation of
/// the same `Dictionary` is undefined behavior (lost writes / heap corruption /
/// EXC_BAD_ACCESS). Routing every access through this wrapper serializes them
/// without changing any call site (it exposes the same subscript / removeAll /
/// removeValue surface the raw dictionaries did). `MWCacheEntry` is a value
/// type, so a subscript read returns a safe snapshot.
final class LockedCache<Value> {
    private let lock = NSLock()
    private var storage: [String: MWCacheEntry<Value>] = [:]

    subscript(key: String) -> MWCacheEntry<Value>? {
        get { lock.lock(); defer { lock.unlock() }; return storage[key] }
        set { lock.lock(); defer { lock.unlock() }; storage[key] = newValue }
    }

    func removeAll() {
        lock.lock(); defer { lock.unlock() }
        storage.removeAll()
    }

    @discardableResult
    func removeValue(forKey key: String) -> MWCacheEntry<Value>? {
        lock.lock(); defer { lock.unlock() }
        return storage.removeValue(forKey: key)
    }

    /// Drop every entry whose key matches `shouldRemove`.
    func removeAll(where shouldRemove: (String) -> Bool) {
        lock.lock(); defer { lock.unlock() }
        for key in storage.keys where shouldRemove(key) {
            storage.removeValue(forKey: key)
        }
    }
}
