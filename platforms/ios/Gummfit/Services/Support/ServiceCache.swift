import Foundation

/// TTL cache entry for values that are safe to reuse for a short window.
struct CacheEntry<Value> {
    let value: Value
    let expiresAt: Date

    var isValid: Bool {
        expiresAt > Date()
    }
}

/// Lock-guarded string-keyed TTL cache. Services are shared, non-isolated
/// singletons whose cache dictionaries would otherwise be bare `var`s
/// mutated from concurrent background `async` methods — concurrent mutation
/// of the same `Dictionary` is undefined behavior. Routing every access
/// through this wrapper serializes them. `CacheEntry` is a value type, so a
/// subscript read returns a safe snapshot.
final class LockedCache<Value> {
    private let lock = NSLock()
    private var storage: [String: CacheEntry<Value>] = [:]

    subscript(key: String) -> CacheEntry<Value>? {
        get { lock.lock(); defer { lock.unlock() }; return storage[key] }
        set { lock.lock(); defer { lock.unlock() }; storage[key] = newValue }
    }

    func removeAll() {
        lock.lock(); defer { lock.unlock() }
        storage.removeAll()
    }

    @discardableResult
    func removeValue(forKey key: String) -> CacheEntry<Value>? {
        lock.lock(); defer { lock.unlock() }
        return storage.removeValue(forKey: key)
    }
}
