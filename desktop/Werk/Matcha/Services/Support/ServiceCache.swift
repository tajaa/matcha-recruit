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
