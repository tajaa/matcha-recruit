import XCTest
@testable import Matcha

/// Covers the detail-VM cache — including `clearAll()`, which is the
/// cross-session data-leak fix: these VMs retain the previous user's loaded
/// data keyed only by entity id, so a logout that doesn't clear them can
/// repaint user A's data for user B on a shared Mac.
///
/// `WorkDetailVMStore` is a `private init()` singleton, so every test drives
/// `.shared` and clears in both `setUp` and `tearDown` to stay isolated.
@MainActor
final class WorkDetailVMStoreTests: XCTestCase {

    override func setUp() async throws {
        WorkDetailVMStore.shared.clearAll()
    }

    override func tearDown() async throws {
        WorkDetailVMStore.shared.clearAll()
    }

    // MARK: - Vending

    func testSameIdReturnsSameInstance() {
        let store = WorkDetailVMStore.shared
        let first = store.channelVM("chan-1")
        let second = store.channelVM("chan-1")
        XCTAssertTrue(first === second, "a warm id must reuse its VM, not cold-load")
    }

    func testDifferentIdsReturnDistinctInstances() {
        let store = WorkDetailVMStore.shared
        XCTAssertFalse(store.channelVM("chan-1") === store.channelVM("chan-2"))
    }

    func testProjectAndThreadVMsAreVendedAndReusedIndependently() {
        let store = WorkDetailVMStore.shared
        let project = store.projectVM("shared-id")
        let thread = store.threadVM("shared-id")

        XCTAssertTrue(store.projectVM("shared-id") === project)
        XCTAssertTrue(store.threadVM("shared-id") === thread)
        // Same raw id, different namespaces — must not collide.
        XCTAssertFalse((project as AnyObject) === (thread as AnyObject))
    }

    // MARK: - Eviction

    func testEvictChannelForcesRebuild() {
        let store = WorkDetailVMStore.shared
        let before = store.channelVM("chan-1")
        store.evictChannel("chan-1")
        XCTAssertFalse(store.channelVM("chan-1") === before)
    }

    func testEvictIsScopedToItsOwnKind() {
        let store = WorkDetailVMStore.shared
        let project = store.projectVM("x")
        let channel = store.channelVM("x")

        store.evictChannel("x")

        XCTAssertTrue(store.projectVM("x") === project, "evicting c:x must not touch p:x")
        XCTAssertFalse(store.channelVM("x") === channel)
    }

    func testEvictWithMalformedKeyIsANoOp() {
        let store = WorkDetailVMStore.shared
        let vm = store.channelVM("chan-1")
        store.evict("no-separator")
        XCTAssertTrue(store.channelVM("chan-1") === vm)
    }

    // MARK: - LRU cap

    /// `cap` is 6. Vending 7 distinct entities must drop the least-recently
    /// used one.
    ///
    /// Note: probing is destructive. Vending an evicted id re-inserts it, which
    /// evicts the next LRU entry in turn — so a single test may make only ONE
    /// cold-probe assertion, and warm-entry checks belong in their own test
    /// (re-vending a warm id only re-touches it, leaving the count at `cap`).
    func testExceedingCapEvictsLeastRecentlyUsed() {
        let store = WorkDetailVMStore.shared
        var vms: [String: ChannelChatViewModel] = [:]
        for i in 0..<6 { vms["c\(i)"] = store.channelVM("c\(i)") }

        store.channelVM("c6") // 7th — pushes c0 (LRU) out

        XCTAssertFalse(store.channelVM("c0") === vms["c0"], "LRU entry should have been evicted")
    }

    /// The other half of the cap behavior: everything newer than the evicted
    /// entry survives. Only warm ids are probed here, so the LRU is never
    /// perturbed and all six assertions stay valid.
    func testExceedingCapKeepsEverythingNewerThanTheEvictedEntry() {
        let store = WorkDetailVMStore.shared
        var vms: [String: ChannelChatViewModel] = [:]
        for i in 0..<6 { vms["c\(i)"] = store.channelVM("c\(i)") }

        let newest = store.channelVM("c6") // evicts c0

        for i in 1..<6 {
            XCTAssertTrue(store.channelVM("c\(i)") === vms["c\(i)"], "c\(i) should still be warm")
        }
        XCTAssertTrue(store.channelVM("c6") === newest, "the newest entry must be warm")
    }

    func testTouchingAnEntryProtectsItFromEviction() {
        let store = WorkDetailVMStore.shared
        var vms: [String: ChannelChatViewModel] = [:]
        for i in 0..<6 { vms["c\(i)"] = store.channelVM("c\(i)") }

        _ = store.channelVM("c0")  // re-touch → c1 becomes LRU
        store.channelVM("c6")

        XCTAssertTrue(store.channelVM("c0") === vms["c0"], "re-touched entry must survive")
        XCTAssertFalse(store.channelVM("c1") === vms["c1"], "c1 is now LRU and should be gone")
    }

    // MARK: - Logout clear (the data-leak fix)

    func testClearAllDropsEveryCachedVMAcrossAllKinds() {
        let store = WorkDetailVMStore.shared
        let project = store.projectVM("p1")
        let thread = store.threadVM("t1")
        let channel = store.channelVM("c1")

        store.clearAll()

        XCTAssertFalse(store.projectVM("p1") === project,
                       "a post-logout re-open must not reuse the prior user's project VM")
        XCTAssertFalse(store.threadVM("t1") === thread,
                       "a post-logout re-open must not reuse the prior user's thread VM")
        XCTAssertFalse(store.channelVM("c1") === channel,
                       "a post-logout re-open must not reuse the prior user's channel VM")
    }

    func testClearAllAlsoResetsLRUBookkeeping() {
        let store = WorkDetailVMStore.shared
        for i in 0..<6 { store.channelVM("c\(i)") }
        store.clearAll()

        // Fill to cap again; if the LRU list had survived the clear, the first
        // of these would be evicted early by stale entries.
        var vms: [String: ChannelChatViewModel] = [:]
        for i in 0..<6 { vms["n\(i)"] = store.channelVM("n\(i)") }
        for i in 0..<6 {
            XCTAssertTrue(store.channelVM("n\(i)") === vms["n\(i)"])
        }
    }
}
