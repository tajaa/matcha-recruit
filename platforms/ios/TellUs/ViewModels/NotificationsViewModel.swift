import Foundation
import Observation

@MainActor
@Observable
final class NotificationsViewModel {
    var items: [TellusNotification] = []
    var isLoading = false
    var error: String?

    func load() async {
        isLoading = true; defer { isLoading = false }
        do {
            items = try await NotificationsService.shared.list(limit: 50)
            error = nil
        } catch {
            if error.isCancellation { return }
            self.error = error.localizedDescription
        }
    }

    func markAllRead() async {
        do {
            try await NotificationsService.shared.markRead(id: nil)
            await load()
        } catch {
            if error.isCancellation { return }
            self.error = error.localizedDescription
        }
    }
}
