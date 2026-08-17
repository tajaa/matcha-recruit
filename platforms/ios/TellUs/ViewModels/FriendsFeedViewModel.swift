import Foundation
import Observation

@MainActor
@Observable
final class FriendsFeedViewModel: LoadableVM {
    var isLoading = false
    var error: String?
    var items: [FriendActivityItem] = []
    var nextCursor: String?
    private var isLoadingMore = false

    func load() async {
        nextCursor = nil
        await withLoad {
            let page = try await FriendsService.shared.feed()
            items = page.items; nextCursor = page.next_cursor
        }
    }

    func loadMore() async {
        guard nextCursor != nil, !isLoadingMore else { return }
        isLoadingMore = true
        defer { isLoadingMore = false }
        do {
            let page = try await FriendsService.shared.feed(cursor: nextCursor)
            items.append(contentsOf: page.items); nextCursor = page.next_cursor
        } catch { /* Keep the loaded feed visible on pagination failure. */ }
    }
}
