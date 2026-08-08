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
    /// contract so the GET set matches what `save()` will PUT-replace.
    func load(siteId: String, locationId: String? = nil) async {
        await withLoad {
            async let existing = CatalogService.shared.listDiscounts(siteId: siteId, locationId: locationId, shared: locationId == nil)
            async let types = BookingsService.shared.listTypes(siteId: siteId)
            async let products = CatalogService.shared.list(siteId: siteId)
            let (fetchedDiscounts, fetchedTypes, fetchedProducts) = try await (existing, types, products)
            self.discounts = fetchedDiscounts.map { CappeDiscountInput(from: $0) }
            self.bookingTypes = fetchedTypes
            self.products = fetchedProducts
        }
    }

    /// Mirrors the server's own check (routes/discounts.py:67-72) — a
    /// scoped discount with no target would 400 the whole set, so disable
    /// Save client-side rather than let the user find out after a round-trip.
    var canSave: Bool {
        discounts.allSatisfy { $0.scope == .all || $0.target_id != nil }
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
