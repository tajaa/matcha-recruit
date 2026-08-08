import Foundation
import Observation

/// Whole-schedule replace, one location at a time — same shape as
/// `DiscountsViewModel`/`RateRulesViewModel`.
@MainActor
@Observable
final class AvailabilityViewModel: LoadableVM {
    var slots: [CappeAvailabilitySlot] = []
    var isLoading = false
    var isSaving = false
    var error: String?

    /// `locationId == nil` loads with `shared: true` — the exact set the
    /// following `save()` (which PUTs with the same nil `locationId`) will
    /// replace. A concrete `locationId` loads that location's rows PLUS the
    /// shared rows (server's `_loc_filter`), so we filter back down to just
    /// `location_id == locationId` here — `save()` can only PUT-replace that
    /// one partition, and re-saving shared rows under a location would
    /// duplicate them (they'd survive under both scopes).
    func load(siteId: String, locationId: String? = nil) async {
        await withLoad {
            self.slots = try await BookingsService.shared.getAvailability(siteId: siteId, locationId: locationId, shared: locationId == nil)
                .filter { locationId == nil || $0.location_id == locationId }
                .map { CappeAvailabilitySlot(weekday: $0.weekday, start_time: $0.start_time, end_time: $0.end_time, booking_type_id: $0.booking_type_id, staff_id: $0.staff_id, location_id: $0.location_id) }
        }
    }

    @discardableResult
    func save(siteId: String, locationId: String? = nil) async -> Bool {
        isSaving = true
        error = nil
        defer { isSaving = false }
        do {
            let saved = try await BookingsService.shared.replaceAvailability(siteId: siteId, locationId: locationId, slots)
            slots = saved.map { CappeAvailabilitySlot(weekday: $0.weekday, start_time: $0.start_time, end_time: $0.end_time, booking_type_id: $0.booking_type_id, staff_id: $0.staff_id, location_id: $0.location_id) }
            return true
        } catch {
            if error.isCancellation { return false }
            self.error = error.localizedDescription
            return false
        }
    }
}
