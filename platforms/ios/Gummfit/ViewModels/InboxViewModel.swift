import Foundation
import Observation

@MainActor
@Observable
final class InboxViewModel: LoadableVM {
    var threads: [CappeThread] = []
    var isLoading = false
    var error: String?

    /// The unread badge itself is polled from `AppState` (plan §5) so it
    /// survives tab switches and pauses while backgrounded — this VM just
    /// loads the list for display.
    func load(siteId: String) async {
        await withLoad {
            self.threads = try await MessagesService.shared.listThreads(siteId: siteId)
        }
    }
}
