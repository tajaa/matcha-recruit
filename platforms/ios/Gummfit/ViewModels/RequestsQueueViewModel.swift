import Foundation
import Observation

/// Backs the pending-requests section on Home (unified accept/decline queue —
/// server/app/cappe/routes/bookings.py:378-419). Removes rows locally on a
/// successful action instead of refetching the whole queue.
@MainActor
@Observable
final class RequestsQueueViewModel: LoadableVM {
    var requests: [CappeRequestSummary] = []
    var isLoading = false
    var error: String?

    func load(siteId: String) async {
        await withLoad {
            self.requests = try await BookingsService.shared.requests(siteId: siteId)
        }
    }

    func accept(siteId: String, _ request: CappeRequestSummary) async {
        do {
            switch request.kind {
            case "booking": _ = try await BookingsService.shared.accept(siteId: siteId, bookingId: request.id)
            case "order": _ = try await OrdersService.shared.accept(siteId: siteId, orderId: request.id)
            default: return
            }
            requests.removeAll { $0.id == request.id }
        } catch {
            if error.isCancellation { return }
            self.error = error.localizedDescription
        }
    }

    func decline(siteId: String, _ request: CappeRequestSummary, reason: String?) async {
        do {
            switch request.kind {
            case "booking": _ = try await BookingsService.shared.decline(siteId: siteId, bookingId: request.id, reason: reason)
            case "order": _ = try await OrdersService.shared.decline(siteId: siteId, orderId: request.id, reason: reason)
            default: return
            }
            requests.removeAll { $0.id == request.id }
        } catch {
            if error.isCancellation { return }
            self.error = error.localizedDescription
        }
    }
}
