import Foundation

/// Mirrors server/app/cappe/models/bookings.py's booking-type/availability/
/// rate-rule/rider/booking shapes + client/src/cappe/types.ts:495-624.
/// Phase 4 (Sales tab — Bookings + Setup). `start_time`/`end_time` are
/// Python `time` (wire "HH:MM:SS") — decoded as String, matching the app's
/// existing "dates/times as String" convention (no Date round-trip risk).

// MARK: - Booking types

struct CappeBookingType: Codable, Identifiable, Equatable {
    let id: String
    let site_id: String
    var name: String
    var description: String?
    var duration_minutes: Int
    var price_cents: Int?
    var status: String
    var requires_approval: Bool = false
    var pricing_mode: String = "flat"
    var category: String?
    var buffer_minutes: Int = 0
    var staff_ids: [String] = []
    var location_id: String?
    let created_at: String
    let updated_at: String
}

struct CappeBookingTypeCreate: Encodable {
    var name: String
    var description: String?
    var duration_minutes: Int = 30
    var price_cents: Int?
    var status: String = "active"
    var requires_approval: Bool = false
    var pricing_mode: String = "flat"
    var category: String?
    var buffer_minutes: Int = 0
    var staff_ids: [String]?
    var location_id: String?
}

struct CappeBookingTypeUpdate: Encodable {
    var name: String?
    var description: String?
    var duration_minutes: Int?
    var price_cents: Int?
    var status: String?
    var requires_approval: Bool?
    var pricing_mode: String?
    var category: String?
    var buffer_minutes: Int?
    var staff_ids: [String]?
    var location_id: String?
}

// MARK: - Availability (whole-schedule replace, per location)

struct CappeAvailabilitySlot: Codable, Identifiable, Equatable {
    let id = UUID()
    var weekday: Int
    var start_time: String
    var end_time: String
    var booking_type_id: String?
    var staff_id: String?
    var location_id: String?

    enum CodingKeys: String, CodingKey {
        case weekday, start_time, end_time, booking_type_id, staff_id, location_id
    }
}

struct CappeAvailabilityReplace: Encodable {
    var slots: [CappeAvailabilitySlot]
}

struct CappeAvailability: Codable, Identifiable, Equatable {
    let id: String
    let weekday: Int
    let start_time: String
    let end_time: String
    let booking_type_id: String?
    let staff_id: String?
    let location_id: String?
}

// MARK: - Bookings

struct CappeBooking: Codable, Identifiable, Equatable {
    let id: String
    let site_id: String
    let booking_type_id: String?
    let staff_id: String?
    let staff_name: String?
    let location_id: String?
    let location_name: String?
    let customer_name: String?
    let customer_email: String?
    let starts_at: String
    let ends_at: String
    var status: BookingStatus
    let note: String?
    var requires_approval: Bool = false
    let quoted_price_cents: Int?
    var approved_at: String?
    var decline_reason: String?
    let rider_acknowledged: Bool
    let created_at: String
    // `rider_snapshot` (freeform JSON array) is not rendered in v1 — omitted.
}

struct CappeBookingStatusUpdate: Encodable {
    var status: String  // pending|confirmed|cancelled|completed
}

// MARK: - Rate rules (dynamic time-of-day pricing)

struct CappeRateRuleInput: Codable, Identifiable, Equatable {
    let id = UUID()
    var label: String
    var booking_type_id: String?
    var weekday: Int?
    var start_time: String
    var end_time: String
    var multiplier: Double = 1.0
    var location_id: String?

    enum CodingKeys: String, CodingKey {
        case label, booking_type_id, weekday, start_time, end_time, multiplier, location_id
    }
}

struct CappeRateRulesReplace: Encodable {
    var rules: [CappeRateRuleInput]
}

struct CappeRateRule: Codable, Identifiable, Equatable {
    let id: String
    let site_id: String
    let booking_type_id: String?
    var label: String
    let weekday: Int?
    var start_time: String
    var end_time: String
    var multiplier: Double
    let location_id: String?
    let created_at: String
}

// MARK: - Rider (Pro, personal creators)

struct CappeRiderItemInput: Codable, Identifiable, Equatable {
    let id = UUID()
    var label: String
    var detail: String?
    var is_required: Bool = true
    var sort_order: Int = 0

    enum CodingKeys: String, CodingKey {
        case label, detail, is_required, sort_order
    }
}

struct CappeRiderReplace: Encodable {
    var items: [CappeRiderItemInput]
}

struct CappeRiderItem: Codable, Identifiable, Equatable {
    let id: String
    let site_id: String
    var label: String
    var detail: String?
    var is_required: Bool
    var sort_order: Int
    let created_at: String
}
