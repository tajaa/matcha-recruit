import Foundation
import Observation

@MainActor
@Observable
final class StockAdjustViewModel {
    var delta = 0
    var reason = "manual"  // manual|restock|damage|return|adjustment
    var note = ""
    var isSaving = false
    var error: String?

    /// Live preview of the resulting balance — clamps at 0, mirroring the
    /// server's own clamp on the stored column (server/app/cappe/models/shop.py:120).
    nonisolated static func preview(current: Int, delta: Int) -> Int {
        max(0, current + delta)
    }

    @discardableResult
    func submit(siteId: String, productId: String, optionId: String? = nil) async -> CappeProduct? {
        isSaving = true
        error = nil
        defer { isSaving = false }
        do {
            return try await CatalogService.shared.adjustStock(
                siteId: siteId, productId: productId,
                CappeStockAdjust(delta: delta, option_id: optionId, reason: reason, note: note.isEmpty ? nil : note)
            )
        } catch {
            if error.isCancellation { return nil }
            self.error = error.localizedDescription
            return nil
        }
    }
}
