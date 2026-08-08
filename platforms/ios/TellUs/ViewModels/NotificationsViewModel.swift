import Foundation
import Observation

@MainActor
@Observable
final class NotificationsViewModel: LoadableVM {
    var items: [TellusNotification] = []
    var isLoading = false
    var error: String?

    func load() async {
        await withLoad {
            items = try await NotificationsService.shared.list(limit: 50)
        }
    }

    func markAllRead() async {
        await withLoad {
            try await NotificationsService.shared.markRead(id: nil)
            items = try await NotificationsService.shared.list(limit: 50)
        }
    }
}
