import Foundation
import Observation

/// Whole-set replace, same shape as `AvailabilityViewModel`/`RateRulesViewModel`
/// — edits a local draft array, PUTs the lot on explicit Save.
@MainActor
@Observable
final class DiscountsViewModel: LoadableVM {
    var discounts: [CappeDiscountInput] = []
    /// Populates the scope-target pickers in `DiscountsView` — a
    /// `booking_type`/`product`-scoped discount must name a target or the
    /// server 400s the whole PUT (routes/discounts.py:67-72).
    var bookingTypes: [CappeBookingType] = []
    var products: [CappeProduct] = []
    var isLoading = false
    var isSaving = false
    var error: String?

    /// See `AvailabilityViewModel.load`'s doc comment — same `shared: true`
    /// contract, and the same client-side filter back down to the exact
    /// partition `save()` will PUT-replace (a concrete location's GET also
    /// returns shared rows, which `save()` must not re-save as location rows).
    func load(siteId: String, locationId: String? = nil) async {
        await withLoad {
            async let existing = CatalogService.shared.listDiscounts(siteId: siteId, locationId: locationId, shared: locationId == nil)
            async let types = BookingsService.shared.listTypes(siteId: siteId)
            async let products = CatalogService.shared.list(siteId: siteId)
            let (fetchedDiscounts, fetchedTypes, fetchedProducts) = try await (existing, types, products)
            self.discounts = fetchedDiscounts
                .filter { locationId == nil || $0.location_id == locationId }
                .map { CappeDiscountInput(from: $0) }
            self.bookingTypes = fetchedTypes
            self.products = fetchedProducts
        }
    }

    /// Mirrors the server's own check (routes/discounts.py:67-72) — a
    /// scoped discount with no target would 400 the whole set, so disable
    /// Save client-side rather than let the user find out after a round-trip.
    /// `.unknown` (a scope value this build doesn't recognize) is left to the
    /// server, which re-validates target requirements for its own scope set —
    /// blocking it here would strand an existing discount with a newer scope.
    var canSave: Bool {
        discounts.allSatisfy { d in
            let scopeIsBounded: Bool = d.scope == .all || d.scope == .unknown
            return scopeIsBounded || d.target_id != nil
        }
    }

    @discardableResult
    func save(siteId: String, locationId: String? = nil) async -> Bool {
        guard canSave else { return false }
        isSaving = true
        error = nil
        defer { isSaving = false }
        do {
            let saved = try await CatalogService.shared.replaceDiscounts(siteId: siteId, locationId: locationId, discounts)
            discounts = saved.map { CappeDiscountInput(from: $0) }
            return true
        } catch {
            if error.isCancellation { return false }
            self.error = error.localizedDescription
            return false
        }
    }
}
