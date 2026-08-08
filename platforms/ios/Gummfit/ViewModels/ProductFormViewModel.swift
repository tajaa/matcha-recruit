import Foundation
import Observation

/// Backs `ProductFormView` for both create and edit — `productId == nil`
/// means create. Draft fields mirror `CappeProductCreate`/`Update` rather
/// than reusing `CappeProduct` directly, since the form edits a subset and
/// needs mutable value types PhotosPicker/pickers can bind to.
@MainActor
@Observable
final class ProductFormViewModel {
    private(set) var productId: String?
    /// Captured on `load(from:)` so `save()` only sends `fulfillment` when it
    /// actually changed — the server deliberately skips the plan-entitlement
    /// gate on an unrelated edit (routes/shop.py:212-217's
    /// `"fulfillment" in body.model_fields_set` check), and re-sending the
    /// unchanged value on every save would defeat that.
    private var originalFulfillment: Fulfillment?

    var name = ""
    var description = ""
    var priceCents = 0
    var currency = "USD"
    var imageUrl: String?
    var sku = ""
    /// nil = untracked/unlimited stock (server column allows NULL). The form
    /// exposes this as a "Track stock" toggle rather than a bare optional
    /// text field — see `ProductFormView`'s Inventory section.
    var isTrackingStock = false
    var inventory = 0
    var lowStockThreshold: Int?
    var status = "draft"
    var fulfillment: Fulfillment = .physical
    var digitalFileUrl = ""
    var bookingTypeId: String?
    var requiresApproval = false
    var category = ""
    var optionGroups: [CappeProductOptionGroupInput] = []

    var isLoading = false
    var isUploadingPhoto = false
    var error: String?

    var canSubmit: Bool {
        !name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && !isLoading
    }

    func load(from product: CappeProduct) {
        productId = product.id
        name = product.name
        description = product.description ?? ""
        priceCents = product.price_cents
        currency = product.currency
        imageUrl = product.image_url
        sku = product.sku ?? ""
        isTrackingStock = product.inventory != nil
        inventory = product.inventory ?? 0
        lowStockThreshold = product.low_stock_threshold
        status = product.status
        fulfillment = product.fulfillment
        originalFulfillment = product.fulfillment
        digitalFileUrl = product.digital_file_url ?? ""
        bookingTypeId = product.booking_type_id
        requiresApproval = product.requires_approval
        category = product.category ?? ""
        optionGroups = product.option_groups.map { group in
            CappeProductOptionGroupInput(
                name: group.name, select_type: group.select_type, required: group.required,
                sort_order: group.sort_order,
                options: group.options.map {
                    CappeProductOptionInput(name: $0.name, price_delta_cents: $0.price_delta_cents, sort_order: $0.sort_order, inventory: $0.inventory)
                }
            )
        }
    }

    func uploadPhoto(data: Data, mimeType: String, filename: String, siteId: String) async {
        isUploadingPhoto = true
        defer { isUploadingPhoto = false }
        do {
            let prepared = try ImagePrep.prepare(data: data, mimeType: mimeType, filename: filename)
            let response = try await UploadService.shared.uploadImage(siteId: siteId, prepared: prepared)
            imageUrl = response.url
        } catch {
            self.error = error.localizedDescription
        }
    }

    /// Returns true on success. `productId == nil` creates; otherwise updates
    /// in place — matches `SitesViewModel.create`'s explicit-success-flag
    /// pattern rather than inferring success from `error == nil`.
    @discardableResult
    func save(siteId: String) async -> Bool {
        isLoading = true
        error = nil
        defer { isLoading = false }
        let trimmedName = name.trimmingCharacters(in: .whitespacesAndNewlines)
        do {
            if let productId {
                // fulfillment: only send when it actually changed, and never
                // send `.unknown` literally — see `originalFulfillment`/
                // `Fulfillment.isWritable` doc comments.
                let fulfillmentToSend: Fulfillment? =
                    (fulfillment != originalFulfillment && fulfillment.isWritable) ? fulfillment : nil
                // booking_type_id only makes sense while fulfillment ==
                // .booking; outside that, leave the column untouched.
                let bookingTypeIdToSend: Clearable<String> = fulfillment == .booking
                    ? (bookingTypeId.map { .value($0) } ?? .clear)
                    : .unset
                _ = try await CatalogService.shared.update(siteId: siteId, productId: productId, CappeProductUpdate(
                    name: trimmedName,
                    description: .from(description, touched: true),
                    price_cents: priceCents, currency: currency,
                    image_url: imageUrl.map { .value($0) } ?? .unset,
                    sku: .from(sku, touched: true),
                    inventory: isTrackingStock ? .value(inventory) : .clear,
                    low_stock_threshold: (isTrackingStock ? lowStockThreshold : nil).map { .value($0) } ?? .clear,
                    status: status, sort_order: nil, fulfillment: fulfillmentToSend,
                    digital_file_url: .from(digitalFileUrl, touched: true),
                    booking_type_id: bookingTypeIdToSend,
                    requires_approval: requiresApproval,
                    category: .from(category, touched: true),
                    option_groups: optionGroups
                ))
            } else {
                _ = try await CatalogService.shared.create(siteId: siteId, CappeProductCreate(
                    name: trimmedName, description: description.isEmpty ? nil : description,
                    price_cents: priceCents, currency: currency, image_url: imageUrl,
                    sku: sku.isEmpty ? nil : sku,
                    inventory: isTrackingStock ? inventory : nil,
                    low_stock_threshold: isTrackingStock ? lowStockThreshold : nil,
                    status: status, fulfillment: fulfillment.isWritable ? fulfillment : .physical,
                    digital_file_url: digitalFileUrl.isEmpty ? nil : digitalFileUrl,
                    booking_type_id: fulfillment == .booking ? bookingTypeId : nil,
                    requires_approval: requiresApproval,
                    category: category.isEmpty ? nil : category, option_groups: optionGroups
                ))
            }
            return true
        } catch {
            if error.isCancellation { return false }
            self.error = error.localizedDescription
            return false
        }
    }
}
