import XCTest
@testable import Matcha

/// Covers the cache primitives introduced to fix the P0 shared-singleton data
/// race: `MatchaWorkService`'s cache dictionaries were bare `var`s mutated from
/// concurrent background `async` methods. `LockedCache` serializes them.
final class ServiceCacheTests: XCTestCase {

    // MARK: - MWCacheEntry.isValid

    func testEntryIsValidWhileUnexpired() {
        let entry = MWCacheEntry(value: 42, expiresAt: Date().addingTimeInterval(60))
        XCTAssertTrue(entry.isValid)
    }

    func testEntryIsInvalidOnceExpired() {
        let entry = MWCacheEntry(value: 42, expiresAt: Date().addingTimeInterval(-1))
        XCTAssertFalse(entry.isValid)
    }

    // MARK: - LockedCache basic surface

    func testSubscriptRoundTrip() {
        let cache = LockedCache<String>()
        XCTAssertNil(cache["missing"])

        cache["a"] = MWCacheEntry(value: "alpha", expiresAt: Date().addingTimeInterval(60))
        XCTAssertEqual(cache["a"]?.value, "alpha")

        cache["a"] = nil
        XCTAssertNil(cache["a"])
    }

    func testRemoveValueReturnsEvictedEntry() {
        let cache = LockedCache<String>()
        cache["a"] = MWCacheEntry(value: "alpha", expiresAt: Date().addingTimeInterval(60))

        let removed = cache.removeValue(forKey: "a")
        XCTAssertEqual(removed?.value, "alpha")
        XCTAssertNil(cache["a"])
        XCTAssertNil(cache.removeValue(forKey: "a"), "second removal has nothing to return")
    }

    func testRemoveAllClearsEverything() {
        let cache = LockedCache<Int>()
        for i in 0..<10 {
            cache["k\(i)"] = MWCacheEntry(value: i, expiresAt: Date().addingTimeInterval(60))
        }
        cache.removeAll()
        for i in 0..<10 { XCTAssertNil(cache["k\(i)"]) }
    }

    // MARK: - Predicate eviction (backs the per-thread PDF invalidation)

    func testRemoveAllWherePrefixEvictsOnlyMatchingKeys() {
        let cache = LockedCache<Data>()
        let exp = Date().addingTimeInterval(60)
        cache["thread-1:1"] = MWCacheEntry(value: Data(), expiresAt: exp)
        cache["thread-1:latest"] = MWCacheEntry(value: Data(), expiresAt: exp)
        cache["thread-2:1"] = MWCacheEntry(value: Data(), expiresAt: exp)

        cache.removeAll { $0.hasPrefix("thread-1:") }

        XCTAssertNil(cache["thread-1:1"])
        XCTAssertNil(cache["thread-1:latest"])
        XCTAssertNotNil(cache["thread-2:1"], "sibling thread's PDF must survive")
    }

    /// `removeAll(where:)` mutates `storage` while iterating `storage.keys`.
    /// Guards against a regression to a form that traps on concurrent mutation.
    func testRemoveAllWhereMatchingEveryKeyDoesNotTrap() {
        let cache = LockedCache<Int>()
        for i in 0..<50 {
            cache["k\(i)"] = MWCacheEntry(value: i, expiresAt: Date().addingTimeInterval(60))
        }
        cache.removeAll { _ in true }
        for i in 0..<50 { XCTAssertNil(cache["k\(i)"]) }
    }

    // MARK: - The actual race the lock exists to prevent

    /// Hammer one cache from many threads at once. Pre-`LockedCache` this shape
    /// (concurrent `Dictionary` mutation) is undefined behavior and crashes
    /// under load; here it must simply survive with a consistent final state.
    func testConcurrentReadWriteDoesNotCorruptStorage() {
        let cache = LockedCache<Int>()
        let iterations = 500

        DispatchQueue.concurrentPerform(iterations: iterations) { i in
            let key = "k\(i % 25)"
            cache[key] = MWCacheEntry(value: i, expiresAt: Date().addingTimeInterval(60))
            _ = cache[key]
            if i % 7 == 0 { cache.removeValue(forKey: key) }
            if i % 50 == 0 { cache.removeAll { $0.hasPrefix("k1") } }
        }

        // No assertion on contents (the interleaving is nondeterministic by
        // design) — surviving the run without a crash or trap IS the assertion.
        // A final write/read must still behave.
        cache["final"] = MWCacheEntry(value: 1, expiresAt: Date().addingTimeInterval(60))
        XCTAssertEqual(cache["final"]?.value, 1)
    }
}
