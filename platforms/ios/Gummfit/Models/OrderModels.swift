import Foundation

/// Mirrors server/app/cappe/models/shop.py's order shapes +
/// client/src/cappe/types.ts:335-384. Phase 4 (Sales tab).

/// Snapshot of a chosen option at purchase — the server writes this exact
/// shape into `CappeOrderItem.selected_options` (services/shop.py), unlike
/// the truly-freeform `intake_answers`/`intake_fields` dicts, which are not
/// decoded anywhere in this app.
struct CappeSelectedOption: Codable, Equatable {
    let group: String
    let name: String
    let price_delta_cents: Int
}

/// Narrow decode of `CappeOrder.shipping_address` — best-effort optional
/// fields, extras ignored on read.
struct CappeShippingAddress: Codable, Equatable {
    var name: String?
    var line1: String?
    var line2: String?
    var city: String?
    var state: String?
    var postal_code: String?
    var country: String?
}

struct CappeOrderItem: Codable, Identifiable, Equatable {
    let id: String
    let product_id: String?
    let title: String
    let unit_price_cents: Int
    let quantity: Int
    let fulfillment: Fulfillment
    var selected_options: [CappeSelectedOption] = []
    var deliverable_url: String?
    let booking_id: String?
}

struct CappeOrder: Codable, Identifiable, Equatable {
    let id: String
    let site_id: String
    var customer_email: String?
    var customer_name: String?
    var status: OrderStatus
    let subtotal_cents: Int
    let tax_cents: Int
    let shipping_cents: Int
    var shipping_address: CappeShippingAddress?
    var carrier: String?
    var tracking_number: String?
    let total_cents: Int?
    let receipt_number: String?
    let currency: String
    let payment_ref: String?
    let note: String?
    var requires_approval: Bool = false
    var approved_at: String?
    var decline_reason: String?
    let created_at: String
    let updated_at: String
    var items: [CappeOrderItem] = []
}

/// PATCH body — status transition and/or tracking edit. At least one field
/// must be present (mirrors the server's model_validator,
/// server/app/cappe/models/shop.py:216-223) — enforced client-side by
/// OrderDetailViewModel before this ever gets encoded, not by this type.
struct CappeOrderStatusUpdate: Encodable {
    /// Never `Clearable` — the server's `_validate_fields` explicitly rejects
    /// an explicit-null status (would clear a NOT NULL column).
    var status: String?
    var carrier: Clearable<String> = .unset
    var tracking_number: Clearable<String> = .unset

    enum CodingKeys: String, CodingKey {
        case status, carrier, tracking_number
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encodeIfPresent(status, forKey: .status)
        try carrier.encode(to: &container, forKey: .carrier)
        try tracking_number.encode(to: &container, forKey: .tracking_number)
    }
}

/// Shared by order-decline and booking-decline (server/app/cappe/models/bookings.py:273-276).
struct CappeApprovalDecline: Encodable {
    var reason: String?
}

struct CappeDeliverableUpdate: Encodable {
    var deliverable_url: String
}

/// One row in the unified accept/decline queue (server/app/cappe/models/shop.py:185-197).
struct CappeRequestSummary: Codable, Identifiable, Equatable {
    let kind: String  // "booking" | "order"
    let id: String
    let customer_name: String?
    let customer_email: String?
    let title: String
    let amount_cents: Int?
    let currency: String
    let starts_at: String?
    let note: String?
    let rider_acknowledged: Bool?
    let created_at: String
}
