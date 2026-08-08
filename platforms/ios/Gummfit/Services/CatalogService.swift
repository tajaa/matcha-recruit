import Foundation

/// Products + stock + discounts (server/app/cappe/routes/shop.py,
/// discounts.py). Same singleton/per-call-siteId shape as `SitesService`.
final class CatalogService {
    static let shared = CatalogService()
    private init() {}

    func list(siteId: String) async throws -> [CappeProduct] {
        try await APIClient.shared.request(method: "GET", path: "/sites/\(siteId)/products")
    }

    func get(siteId: String, productId: String) async throws -> CappeProduct {
        try await APIClient.shared.request(method: "GET", path: "/sites/\(siteId)/products/\(productId)")
    }

    func create(siteId: String, _ body: CappeProductCreate) async throws -> CappeProduct {
        try await APIClient.shared.request(method: "POST", path: "/sites/\(siteId)/products", body: body)
    }

    func update(siteId: String, productId: String, _ body: CappeProductUpdate) async throws -> CappeProduct {
        try await APIClient.shared.request(method: "PUT", path: "/sites/\(siteId)/products/\(productId)", body: body)
    }

    func delete(siteId: String, productId: String) async throws {
        try await APIClient.shared.requestVoid(method: "DELETE", path: "/sites/\(siteId)/products/\(productId)")
    }

    func adjustStock(siteId: String, productId: String, _ body: CappeStockAdjust) async throws -> CappeProduct {
        try await APIClient.shared.request(method: "POST", path: "/sites/\(siteId)/products/\(productId)/adjust", body: body)
    }

    func inventoryLog(siteId: String, productId: String) async throws -> [CappeInventoryAdjustment] {
        try await APIClient.shared.request(method: "GET", path: "/sites/\(siteId)/products/\(productId)/inventory-log")
    }

    func listDiscounts(siteId: String, locationId: String? = nil, shared: Bool = false) async throws -> [CappeDiscount] {
        try await APIClient.shared.request(method: "GET", path: "/sites/\(siteId)/discounts" + LocationQuery.string(locationId, shared: shared))
    }

    /// Replaces the discount set FOR ONE LOCATION (nil = shared) — others untouched.
    func replaceDiscounts(siteId: String, locationId: String? = nil, _ discounts: [CappeDiscountInput]) async throws -> [CappeDiscount] {
        try await APIClient.shared.request(
            method: "PUT",
            path: "/sites/\(siteId)/discounts" + LocationQuery.string(locationId),
            body: CappeDiscountReplace(discounts: discounts)
        )
    }
}
