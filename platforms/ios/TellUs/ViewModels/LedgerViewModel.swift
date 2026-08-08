import Foundation
import Observation

/// Extracted out of LedgerView, which held this paging state (with `try?`,
/// no error surfaced) directly in the View — VMs own state, Views render it.
@MainActor
@Observable
final class LedgerViewModel: LoadableVM {
    var entries: [LedgerEntry] = []
    var isLoading = false
    var error: String?
    var hasMore = true

    private let pageSize = 50
    private var offset = 0

    func loadMore() async {
        if isLoading { return }
        guard hasMore else { return }
        await withLoad {
            let page = try await RewardsService.shared.ledger(limit: pageSize, offset: offset)
            entries += page
            offset += page.count
            hasMore = page.count == pageSize
        }
    }
}
