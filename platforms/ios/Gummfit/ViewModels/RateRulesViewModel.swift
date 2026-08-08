import Foundation
import Observation

@MainActor
@Observable
final class RateRulesViewModel: LoadableVM {
    var rules: [CappeRateRuleInput] = []
    var isLoading = false
    var isSaving = false
    var error: String?

    /// See `AvailabilityViewModel.load`'s doc comment — same `shared: true`
    /// contract so the GET set matches what `save()` will PUT-replace.
    func load(siteId: String, locationId: String? = nil) async {
        await withLoad {
            self.rules = try await BookingsService.shared.rateRules(siteId: siteId, locationId: locationId, shared: locationId == nil)
                .map { CappeRateRuleInput(label: $0.label, booking_type_id: $0.booking_type_id, weekday: $0.weekday, start_time: $0.start_time, end_time: $0.end_time, multiplier: $0.multiplier, location_id: $0.location_id) }
        }
    }

    @discardableResult
    func save(siteId: String, locationId: String? = nil) async -> Bool {
        isSaving = true
        error = nil
        defer { isSaving = false }
        do {
            let saved = try await BookingsService.shared.replaceRateRules(siteId: siteId, locationId: locationId, rules)
            rules = saved.map { CappeRateRuleInput(label: $0.label, booking_type_id: $0.booking_type_id, weekday: $0.weekday, start_time: $0.start_time, end_time: $0.end_time, multiplier: $0.multiplier, location_id: $0.location_id) }
            return true
        } catch {
            if error.isCancellation { return false }
            self.error = error.localizedDescription
            return false
        }
    }
}
