import Foundation

/// Mirrors server/app/cappe/models/shop.py + client/src/cappe/types.ts:254-343.
/// Product/inventory/discount shapes for the Catalog tab (Phase 3).

// MARK: - Product option groups (Size, Milk, Add-ons)

struct CappeProductOption: Codable, Identifiable, Equatable {
    let id: String
    var name: String
    var price_delta_cents: Int = 0
    var sort_order: Int = 0
    var inventory: Int?
}

struct CappeProductOptionGroup: Codable, Identifiable, Equatable {
    let id: String
    var name: String
    var select_type: String = "single"
    var required: Bool = false
    var sort_order: Int = 0
    var options: [CappeProductOption] = []
}

/// Write-side — no `id`; the whole set is replaced on product create/update
/// (server/app/cappe/models/shop.py:20-33).
struct CappeProductOptionInput: Codable, Identifiable, Equatable {
    let id = UUID()
    var name: String
    var price_delta_cents: Int = 0
    var sort_order: Int = 0
    var inventory: Int?

    enum CodingKeys: String, CodingKey {
        case name, price_delta_cents, sort_order, inventory
    }
}

struct CappeProductOptionGroupInput: Codable, Identifiable, Equatable {
    let id = UUID()
    var name: String
    var select_type: String = "single"
    var required: Bool = false
    var sort_order: Int = 0
    var options: [CappeProductOptionInput] = []

    enum CodingKeys: String, CodingKey {
        case name, select_type, required, sort_order, options
    }
}

// MARK: - Product

struct CappeProduct: Codable, Identifiable, Equatable {
    let id: String
    let site_id: String
    var name: String
    var description: String?
    var price_cents: Int
    var currency: String
    var image_url: String?
    var sku: String?
    var inventory: Int?
    var low_stock_threshold: Int?
    var status: String
    var sort_order: Int
    var fulfillment: Fulfillment
    var digital_file_url: String?
    var booking_type_id: String?
    var requires_approval: Bool = false
    var category: String?
    var option_groups: [CappeProductOptionGroup] = []
    // `intake_fields` (freeform per-product questions) is deliberately not
    // decoded — JSONDecoder ignores unknown wire fields, and create/update
    // never sends the key, leaving server defaults ([]).
}

/// Write-side — only the fields the product form actually edits.
struct CappeProductCreate: Encodable {
    var name: String
    var description: String?
    var price_cents: Int = 0
    var currency: String = "USD"
    var image_url: String?
    var sku: String?
    var inventory: Int?
    var low_stock_threshold: Int?
    var status: String = "draft"
    var sort_order: Int = 0
    var fulfillment: Fulfillment = .physical
    var digital_file_url: String?
    var booking_type_id: String?
    var requires_approval: Bool = false
    var category: String?
    var option_groups: [CappeProductOptionGroupInput]?
}

/// Write-side — only the fields the product form actually edits. Fields the
/// server's `cappe_products` schema allows NULL on go through `Clearable` so
/// emptying them in the form actually clears the column instead of silently
/// no-op'ing (see `Clearable`'s doc comment).
struct CappeProductUpdate: Encodable {
    var name: String?
    var description: Clearable<String> = .unset
    var price_cents: Int?
    var currency: String?
    var image_url: Clearable<String> = .unset
    var sku: Clearable<String> = .unset
    var inventory: Clearable<Int> = .unset
    var low_stock_threshold: Clearable<Int> = .unset
    var status: String?
    var sort_order: Int?
    var fulfillment: Fulfillment?
    var digital_file_url: Clearable<String> = .unset
    var booking_type_id: Clearable<String> = .unset
    var requires_approval: Bool?
    var category: Clearable<String> = .unset
    var option_groups: [CappeProductOptionGroupInput]?

    enum CodingKeys: String, CodingKey {
        case name, description, price_cents, currency, image_url, sku, inventory,
             low_stock_threshold, status, sort_order, fulfillment, digital_file_url,
             booking_type_id, requires_approval, category, option_groups
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encodeIfPresent(name, forKey: .name)
        try description.encode(to: &container, forKey: .description)
        try container.encodeIfPresent(price_cents, forKey: .price_cents)
        try container.encodeIfPresent(currency, forKey: .currency)
        try image_url.encode(to: &container, forKey: .image_url)
        try sku.encode(to: &container, forKey: .sku)
        try inventory.encode(to: &container, forKey: .inventory)
        try low_stock_threshold.encode(to: &container, forKey: .low_stock_threshold)
        try container.encodeIfPresent(status, forKey: .status)
        try container.encodeIfPresent(sort_order, forKey: .sort_order)
        try container.encodeIfPresent(fulfillment, forKey: .fulfillment)
        try digital_file_url.encode(to: &container, forKey: .digital_file_url)
        try booking_type_id.encode(to: &container, forKey: .booking_type_id)
        try container.encodeIfPresent(requires_approval, forKey: .requires_approval)
        try category.encode(to: &container, forKey: .category)
        try container.encodeIfPresent(option_groups, forKey: .option_groups)
    }
}

// MARK: - Stock / inventory

/// Manual stock change from the owner (server/app/cappe/models/shop.py:118-123).
struct CappeStockAdjust: Encodable {
    var delta: Int
    var option_id: String?
    var reason: String = "manual"  // manual|restock|damage|return|adjustment
    var note: String?
}

struct CappeInventoryAdjustment: Codable, Identifiable, Equatable {
    let id: String
    let product_id: String
    let option_id: String?
    let delta: Int
    let balance_after: Int?
    let reason: String
    let note: String?
    let created_at: String
}

// MARK: - Discounts

struct CappeDiscount: Codable, Identifiable, Equatable {
    let id: String
    let site_id: String
    var label: String
    var percent_off: Int
    var scope: DiscountScope
    var target_id: String?
    var active: Bool
    var starts_on: String?
    var ends_on: String?
    var location_id: String?
    let created_at: String
}

/// Write-side row for the whole-set discount replace (server/app/cappe/models/shop.py:290-298).
struct CappeDiscountInput: Codable, Identifiable, Equatable {
    let id = UUID()
    var label: String = "Discount"
    var percent_off: Int
    var scope: DiscountScope = .all
    var target_id: String?
    var active: Bool = true
    var starts_on: String?
    var ends_on: String?
    var location_id: String?

    enum CodingKeys: String, CodingKey {
        case label, percent_off, scope, target_id, active, starts_on, ends_on, location_id
    }

    init(from existing: CappeDiscount) {
        label = existing.label
        percent_off = existing.percent_off
        scope = existing.scope
        target_id = existing.target_id
        active = existing.active
        starts_on = existing.starts_on
        ends_on = existing.ends_on
        location_id = existing.location_id
    }

    init(percent_off: Int) {
        self.percent_off = percent_off
    }
}

/// Wire wrapper for the whole-set PUT — the server expects `{discounts:[...]}`,
/// not a bare array (server/app/cappe/models/shop.py:301-302).
struct CappeDiscountReplace: Encodable {
    var discounts: [CappeDiscountInput]
}
