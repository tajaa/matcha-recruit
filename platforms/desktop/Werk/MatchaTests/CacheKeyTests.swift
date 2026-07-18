import XCTest
@testable import Matcha

/// Cache-key construction plus the TTL read guard. These are small, but a
/// mismatch between a key and the prefix predicate that invalidates it is a
/// silent stale-data bug, so the pairing is asserted directly.
final class CacheKeyTests: XCTestCase {

    private var service: MatchaWorkService { MatchaWorkService.shared }

    // MARK: - cachedValue TTL guard

    func testCachedValueReturnsFreshEntry() {
        let entry = MWCacheEntry(value: [1, 2, 3], expiresAt: Date().addingTimeInterval(60))
        XCTAssertEqual(service.cachedValue(entry), [1, 2, 3])
    }

    func testCachedValueDropsExpiredEntry() {
        let entry = MWCacheEntry(value: [1, 2, 3], expiresAt: Date().addingTimeInterval(-1))
        XCTAssertNil(service.cachedValue(entry))
    }

    func testCachedValueHandlesMissingEntry() {
        let missing: MWCacheEntry<[Int]>? = nil
        XCTAssertNil(service.cachedValue(missing))
    }

    // MARK: - List keys

    func testListCacheKeyUsesSentinelForNilStatus() {
        XCTAssertEqual(service.makeListCacheKey(status: nil), "__all__")
    }

    func testListCacheKeyPassesStatusThrough() {
        XCTAssertEqual(service.makeListCacheKey(status: "active"), "active")
    }

    func testListCacheKeysAreDistinctPerStatus() {
        XCTAssertNotEqual(service.makeListCacheKey(status: "active"),
                          service.makeListCacheKey(status: "archived"))
        XCTAssertNotEqual(service.makeListCacheKey(status: nil),
                          service.makeListCacheKey(status: "active"))
    }

    // MARK: - PDF keys

    func testPDFCacheKeyIncludesVersion() {
        XCTAssertEqual(service.makePDFCacheKey(threadId: "t1", version: 3), "t1:3")
    }

    func testPDFCacheKeyUsesLatestSentinelForNilVersion() {
        XCTAssertEqual(service.makePDFCacheKey(threadId: "t1", version: nil), "t1:latest")
    }

    /// The invalidation path evicts with `hasPrefix("\(threadId):")`. Every key
    /// this helper can produce for a thread must match that predicate, and no
    /// key for a different thread may — including the id-prefix case
    /// ("t1" vs "t10") that a naive prefix check would over-match.
    func testEveryPDFKeyForAThreadMatchesItsInvalidationPrefix() {
        let prefix = "t1:"
        for version: Int? in [nil, 1, 2, 99] {
            let key = service.makePDFCacheKey(threadId: "t1", version: version)
            XCTAssertTrue(key.hasPrefix(prefix), "\(key) would survive invalidation of t1")
        }
        for version: Int? in [nil, 1] {
            let other = service.makePDFCacheKey(threadId: "t10", version: version)
            XCTAssertFalse(other.hasPrefix(prefix), "\(other) must not be evicted with t1")
        }
    }
}

/// `stableKey` is the SwiftUI `ForEach` identity that has to survive the
/// optimistic→confirmed message swap; if it changes mid-swap the row flickers
/// and the scroll position jumps.
final class ChannelMessageStableKeyTests: XCTestCase {

    private func message(id: String, clientMessageId: String?) -> ChannelMessage {
        ChannelMessage(
            id: id,
            channelId: "chan-1",
            senderId: "user-1",
            senderName: "Test User",
            senderAvatarUrl: nil,
            content: "hello",
            attachments: [],
            createdAt: "2026-07-18T00:00:00Z",
            editedAt: nil,
            clientMessageId: clientMessageId
        )
    }

    func testPrefersClientMessageId() {
        XCTAssertEqual(message(id: "server-1", clientMessageId: "cmid-1").stableKey, "cmid:cmid-1")
    }

    func testFallsBackToIdWhenNoClientMessageId() {
        XCTAssertEqual(message(id: "server-1", clientMessageId: nil).stableKey, "id:server-1")
    }

    func testEmptyClientMessageIdFallsBackToId() {
        XCTAssertEqual(message(id: "server-1", clientMessageId: "").stableKey, "id:server-1",
                       "an empty cmid must not collapse every such row onto the key \"cmid:\"")
    }

    /// The property that matters: the pending row and its server echo share a
    /// cmid, so the key is unchanged across the swap.
    func testKeyIsStableAcrossOptimisticToConfirmedSwap() {
        let pending = message(id: "local-temp", clientMessageId: "cmid-1")
        let confirmed = message(id: "server-1", clientMessageId: "cmid-1")
        XCTAssertEqual(pending.stableKey, confirmed.stableKey)
    }

    func testDistinctMessagesGetDistinctKeys() {
        XCTAssertNotEqual(message(id: "a", clientMessageId: nil).stableKey,
                          message(id: "b", clientMessageId: nil).stableKey)
        XCTAssertNotEqual(message(id: "a", clientMessageId: "x").stableKey,
                          message(id: "a", clientMessageId: "y").stableKey)
    }
}
