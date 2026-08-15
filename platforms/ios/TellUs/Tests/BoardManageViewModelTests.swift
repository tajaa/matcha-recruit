import XCTest
@testable import TellUs

@MainActor
final class BoardManageViewModelTests: XCTestCase {
    private func makePost(id: String = "p1") -> BoardPost {
        BoardPost(
            id: id, kind: .update, title: "Test post", body: nil, listing: nil,
            event_starts_at: nil, event_ends_at: nil, is_pinned: false,
            moderation_status: "visible", approved_reply_count: 0, held_reply_count: nil,
            created_at: "2026-01-01T00:00:00Z", like_count: nil, liked_by_me: nil
        )
    }

    func testUpdateSlugInvalidatesPostsTab() {
        let vm = BoardManageViewModel(brandId: nil, slug: "old-slug")
        _ = vm.loadState.begin(.posts)
        vm.loadState.succeed(.posts)
        vm.posts = [makePost()]

        vm.updateSlug("new-slug")

        XCTAssertEqual(vm.loadState.phase(.posts), .idle)
        XCTAssertTrue(vm.posts.isEmpty)
    }

    func testUpdateSlugIsNoopWhenUnchanged() {
        let vm = BoardManageViewModel(brandId: nil, slug: "same-slug")
        _ = vm.loadState.begin(.posts)
        vm.loadState.succeed(.posts)
        vm.posts = [makePost()]

        vm.updateSlug("same-slug")

        XCTAssertEqual(vm.loadState.phase(.posts), .loaded)
        XCTAssertEqual(vm.posts.count, 1)
    }

    func testLoadPostsWithNilSlugFailsInsteadOfSilentlyNoOping() async {
        // Guards on `self.slug` before any network call, so this stays offline.
        let vm = BoardManageViewModel(brandId: nil, slug: nil)

        await vm.loadTab(.posts)

        XCTAssertEqual(vm.loadState.phase(.posts), .failed)
        XCTAssertNotNil(vm.error)
    }
}
