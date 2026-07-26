import XCTest
@testable import Matcha

/// Covers `ChannelChatViewModel.refreshMerge` / `.olderPageMerge` — the history
/// paging and silent-refresh logic. This is the highest-risk logic in the
/// channel VM: it decides what a reader sees after a refocus, and it has to
/// reconcile three sources at once (paged-in history, the server's newest page,
/// and local optimistic rows the server hasn't echoed yet).
final class ChannelMergeTests: XCTestCase {

    private let pageSize = 50

    // MARK: - Fixtures

    private func msg(
        _ id: String,
        pending: Bool = false,
        failed: Bool = false,
        cmid: String? = nil,
        createdAt: String = "2026-07-18T00:00:00Z"
    ) -> ChannelMessage {
        ChannelMessage(
            id: id,
            channelId: "chan-1",
            senderId: "user-1",
            senderName: "Test User",
            senderAvatarUrl: nil,
            content: "msg \(id)",
            attachments: [],
            createdAt: createdAt,
            editedAt: nil,
            clientMessageId: cmid,
            pending: pending,
            failed: failed
        )
    }

    private func page(_ count: Int, from start: Int = 0) -> [ChannelMessage] {
        (start..<(start + count)).map { msg("m\($0)") }
    }

    private func ids(_ messages: [ChannelMessage]) -> [String] { messages.map(\.id) }

    // MARK: - refreshMerge: no-change case

    func testIdenticalPageIsNotAChange() {
        let existing = page(3)
        let merge = ChannelChatViewModel.refreshMerge(
            existing: existing, newest: existing, hasMoreHistory: false, pageSize: pageSize
        )
        XCTAssertFalse(merge.changed, "reassigning an identical list rebuilds the view (flash)")
        XCTAssertFalse(merge.scrollToLatest)
    }

    // MARK: - refreshMerge: paged-in history preservation

    /// The core regression this guards: history paged in via loadOlder() must
    /// survive a refresh, not be replaced by the newest page alone.
    func testPagedInHistoryIsPreservedWhenNewestPageOverlaps() {
        let history = page(3)                    // m0,m1,m2 — paged in earlier
        let existing = history + page(2, from: 3) // + m3,m4 (the newest page)
        let newest = page(3, from: 3)            // m3,m4,m5 — server's newest

        let merge = ChannelChatViewModel.refreshMerge(
            existing: existing, newest: newest, hasMoreHistory: true, pageSize: pageSize
        )

        XCTAssertTrue(merge.changed)
        XCTAssertEqual(ids(merge.messages), ["m0", "m1", "m2", "m3", "m4", "m5"],
                       "paged-in history must not be yanked out from under the reader")
    }

    func testOverlappingRefreshLeavesHasMoreHistoryUntouched() {
        let existing = page(4)
        let newest = page(3, from: 1) // overlaps m1..m3
        for flag in [true, false] {
            let merge = ChannelChatViewModel.refreshMerge(
                existing: existing, newest: newest, hasMoreHistory: flag, pageSize: pageSize
            )
            XCTAssertEqual(merge.hasMoreHistory, flag,
                           "an overlapping merge must not restate the paging flag")
        }
    }

    // MARK: - refreshMerge: no-overlap fallback

    /// More than a full page arrived while away, so the gap between kept
    /// history and the newest page is unknowable — fall back to the newest
    /// page alone and recompute the flag.
    func testNoOverlapDiscardsHistoryAndRecomputesFlagForFullPage() {
        let existing = page(5)                    // m0..m4
        let newest = page(pageSize, from: 100)    // wholly disjoint, full page

        let merge = ChannelChatViewModel.refreshMerge(
            existing: existing, newest: newest, hasMoreHistory: false, pageSize: pageSize
        )

        XCTAssertEqual(ids(merge.messages), ids(newest), "unknowable gap → newest page alone")
        XCTAssertTrue(merge.hasMoreHistory, "a full page back implies more history exists")
    }

    func testNoOverlapWithShortPageClearsHasMoreHistory() {
        let merge = ChannelChatViewModel.refreshMerge(
            existing: page(5), newest: page(3, from: 100), hasMoreHistory: true, pageSize: pageSize
        )
        XCTAssertFalse(merge.hasMoreHistory, "a short page back means no older history")
    }

    // MARK: - refreshMerge: optimistic rows

    func testUnechoedPendingAndFailedRowsSurviveAtTheTail() {
        let existing = page(2) + [msg("p1", pending: true, cmid: "c1"),
                                  msg("f1", failed: true, cmid: "c2")]
        let newest = page(3) // m0,m1,m2 — overlaps, no echo for p1/f1 yet

        let merge = ChannelChatViewModel.refreshMerge(
            existing: existing, newest: newest, hasMoreHistory: false, pageSize: pageSize
        )

        XCTAssertEqual(ids(merge.messages), ["m0", "m1", "m2", "p1", "f1"],
                       "in-flight local rows must not vanish under a refresh")
    }

    func testEchoedPendingRowIsNotDuplicated() {
        // The server echo arrives carrying the same id the optimistic row took.
        let existing = page(2) + [msg("m2", pending: true, cmid: "c1")]
        let newest = page(3) // m2 is now confirmed server-side

        let merge = ChannelChatViewModel.refreshMerge(
            existing: existing, newest: newest, hasMoreHistory: false, pageSize: pageSize
        )

        XCTAssertEqual(ids(merge.messages), ["m0", "m1", "m2"], "no duplicate row after echo")
        XCTAssertFalse(merge.messages.last?.pending ?? true, "server version replaces the pending one")
    }

    /// A pending row must never be mistaken for paged-in history and pulled to
    /// the front of the list.
    func testPendingRowIsNotTreatedAsHistoryPrefix() {
        let existing = [msg("p1", pending: true, cmid: "c1")] + page(2)
        let newest = page(2)

        let merge = ChannelChatViewModel.refreshMerge(
            existing: existing, newest: newest, hasMoreHistory: false, pageSize: pageSize
        )

        XCTAssertEqual(ids(merge.messages), ["m0", "m1", "p1"])
    }

    // MARK: - refreshMerge: scroll signalling

    /// New messages arrived above a pending row pinned at the tail. The view's
    /// last-identity scroll trigger can't see this, so the merge must signal.
    func testScrollIsSignalledWhenNewMessagesLandAboveAPinnedTail() {
        let pending = msg("p1", pending: true, cmid: "c1")
        let existing = page(2) + [pending]
        let newest = page(3) // m2 is new

        let merge = ChannelChatViewModel.refreshMerge(
            existing: existing, newest: newest, hasMoreHistory: false, pageSize: pageSize
        )

        XCTAssertTrue(merge.changed)
        XCTAssertTrue(merge.scrollToLatest)
        XCTAssertEqual(merge.messages.last?.stableKey, pending.stableKey, "tail stayed pinned")
    }

    func testScrollIsNotSignalledWhenTheTailItselfChanged() {
        // A changed tail is already handled by the view's identity trigger;
        // signalling here would double-scroll.
        let merge = ChannelChatViewModel.refreshMerge(
            existing: page(2), newest: page(3), hasMoreHistory: false, pageSize: pageSize
        )
        XCTAssertTrue(merge.changed)
        XCTAssertFalse(merge.scrollToLatest)
    }

    /// A deletion-only merge must not yank a reader out of the history they're
    /// reading.
    func testScrollIsNotSignalledForADeletionOnlyMerge() {
        let existing = page(3)
        let newest = [msg("m0"), msg("m2")] // m1 deleted server-side

        let merge = ChannelChatViewModel.refreshMerge(
            existing: existing, newest: newest, hasMoreHistory: false, pageSize: pageSize
        )

        XCTAssertTrue(merge.changed)
        XCTAssertFalse(merge.scrollToLatest, "no new messages → no forced scroll")
    }

    // MARK: - refreshMerge: edge cases

    func testEmptyExistingTakesTheNewestPage() {
        let merge = ChannelChatViewModel.refreshMerge(
            existing: [], newest: page(3), hasMoreHistory: false, pageSize: pageSize
        )
        XCTAssertTrue(merge.changed)
        XCTAssertEqual(ids(merge.messages), ["m0", "m1", "m2"])
    }

    func testEmptyNewestPageKeepsOnlyUnechoedLocalRows() {
        let existing = page(2) + [msg("p1", pending: true, cmid: "c1")]
        let merge = ChannelChatViewModel.refreshMerge(
            existing: existing, newest: [], hasMoreHistory: false, pageSize: pageSize
        )
        // No overlap with an empty page → history is discarded, but the
        // in-flight row is still the user's unsent work.
        XCTAssertEqual(ids(merge.messages), ["p1"])
        XCTAssertFalse(merge.hasMoreHistory)
    }

    // MARK: - olderPageMerge

    func testOlderPageFiltersRowsAlreadyOnScreen() {
        let existing = page(3, from: 3)      // m3,m4,m5
        let older = page(4, from: 1)         // m1..m4 — m3,m4 already shown

        let result = ChannelChatViewModel.olderPageMerge(
            existing: existing, older: older, pageSize: pageSize
        )

        XCTAssertEqual(ids(result.fresh), ["m1", "m2"], "duplicates must not be prepended")
    }

    func testFullFreshPageMeansMoreHistoryRemains() {
        let result = ChannelChatViewModel.olderPageMerge(
            existing: page(1, from: 100), older: page(pageSize), pageSize: pageSize
        )
        XCTAssertTrue(result.hasMoreHistory)
        XCTAssertEqual(result.fresh.count, pageSize)
    }

    func testShortPageEndsHistory() {
        let result = ChannelChatViewModel.olderPageMerge(
            existing: page(1, from: 100), older: page(3), pageSize: pageSize
        )
        XCTAssertFalse(result.hasMoreHistory, "a short page means the end was reached")
    }

    /// A full page that is entirely duplicates would otherwise leave
    /// `hasMoreHistory` true forever with nothing new to show — an infinite
    /// "Load older" button.
    func testAllDuplicatePageEndsHistoryEvenWhenFull() {
        let existing = page(pageSize)
        let result = ChannelChatViewModel.olderPageMerge(
            existing: existing, older: existing, pageSize: pageSize
        )
        XCTAssertTrue(result.fresh.isEmpty)
        XCTAssertFalse(result.hasMoreHistory, "an all-duplicates page must not loop forever")
    }

    func testEmptyPageEndsHistory() {
        let result = ChannelChatViewModel.olderPageMerge(
            existing: page(3), older: [], pageSize: pageSize
        )
        XCTAssertTrue(result.fresh.isEmpty)
        XCTAssertFalse(result.hasMoreHistory)
    }
}
