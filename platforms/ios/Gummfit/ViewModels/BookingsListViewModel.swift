import Foundation
import Observation

@MainActor
@Observable
final class BookingsListViewModel: LoadableVM {
    var bookings: [CappeBooking] = []
    var isLoading = false
    var error: String?

    func load(siteId: String) async {
        await withLoad {
            self.bookings = try await BookingsService.shared.list(siteId: siteId)
        }
    }

    func accept(siteId: String, bookingId: String) async {
        do {
            let updated = try await BookingsService.shared.accept(siteId: siteId, bookingId: bookingId)
            if let idx = bookings.firstIndex(where: { $0.id == bookingId }) { bookings[idx] = updated }
        } catch {
            if error.isCancellation { return }
            self.error = error.localizedDescription
        }
    }

    func decline(siteId: String, bookingId: String, reason: String?) async {
        do {
            let updated = try await BookingsService.shared.decline(siteId: siteId, bookingId: bookingId, reason: reason)
            if let idx = bookings.firstIndex(where: { $0.id == bookingId }) { bookings[idx] = updated }
        } catch {
            if error.isCancellation { return }
            self.error = error.localizedDescription
        }
    }
}
