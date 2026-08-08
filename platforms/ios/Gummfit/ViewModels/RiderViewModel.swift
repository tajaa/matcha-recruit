import Foundation
import Observation

/// Rider editing is a paid personal-creator capability — reads are open, but
/// a write can 403 (business account) or 402 (unentitled plan); both surface
/// through the ordinary `APIError.httpError`/`.paymentRequired` cases, no new
/// error handling needed here (server/app/cappe/routes/rider.py:31-47).
@MainActor
@Observable
final class RiderViewModel: LoadableVM {
    var items: [CappeRiderItemInput] = []
    var isLoading = false
    var isSaving = false
    var error: String?

    func load(siteId: String) async {
        await withLoad {
            self.items = try await BookingsService.shared.rider(siteId: siteId)
                .map { CappeRiderItemInput(label: $0.label, detail: $0.detail, is_required: $0.is_required, sort_order: $0.sort_order) }
        }
    }

    @discardableResult
    func save(siteId: String) async -> Bool {
        isSaving = true
        error = nil
        defer { isSaving = false }
        do {
            let saved = try await BookingsService.shared.replaceRider(siteId: siteId, items)
            items = saved.map { CappeRiderItemInput(label: $0.label, detail: $0.detail, is_required: $0.is_required, sort_order: $0.sort_order) }
            return true
        } catch {
            if error.isCancellation { return false }
            self.error = error.localizedDescription
            return false
        }
    }
}
