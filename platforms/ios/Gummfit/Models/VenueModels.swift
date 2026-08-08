import Foundation

/// Mirrors server/app/cappe/models/bookings.py's location/staff shapes +
/// client/src/cappe/types.ts:448-493. Phase 5 (Venue screen, multi-location
/// sites only — `site.is_multi_location`).

struct CappeLocationHours: Codable, Identifiable, Equatable {
    let id = UUID()
    var day: Int  // Mon=0..Sun=6
    var open: String?
    var close: String?
    var closed: Bool = false

    enum CodingKeys: String, CodingKey {
        case day, open, close, closed
    }
}

struct CappeLocation: Codable, Identifiable, Equatable {
    let id: String
    let site_id: String
    var name: String
    var address: String?
    var lat: Double?
    var lng: Double?
    let city: String?      // server-derived (background geocoder), not client-settable
    let region: String?
    var timezone: String?
    var hours: [CappeLocationHours] = []
    var contact_phone: String?
    var contact_email: String?
    var is_default: Bool = false
    var active: Bool = true
    var sort_order: Int = 0
    let created_at: String
    let updated_at: String
}

struct CappeLocationCreate: Encodable {
    var name: String
    var address: String?
    var lat: Double?
    var lng: Double?
    var timezone: String?
    var hours: [CappeLocationHours] = []
    var contact_phone: String?
    var contact_email: String?
    var is_default: Bool = false
    var active: Bool = true
    var sort_order: Int = 0
}

struct CappeLocationUpdate: Encodable {
    var name: String?
    var address: String?
    var lat: Double?
    var lng: Double?
    var timezone: String?
    var hours: [CappeLocationHours]?
    var contact_phone: String?
    var contact_email: String?
    var is_default: Bool?
    var active: Bool?
    var sort_order: Int?
}

struct CappeStaff: Codable, Identifiable, Equatable {
    let id: String
    let site_id: String
    var name: String
    var bio: String?
    var image_url: String?
    var active: Bool = true
    var sort_order: Int = 0
    var location_id: String?  // nil = works at all locations
    let created_at: String
    let updated_at: String
}

struct CappeStaffCreate: Encodable {
    var name: String
    var bio: String?
    var image_url: String?
    var active: Bool = true
    var sort_order: Int = 0
    var location_id: String?
}

struct CappeStaffUpdate: Encodable {
    var name: String?
    var bio: String?
    var image_url: String?
    var active: Bool?
    var sort_order: Int?
    var location_id: String?
}
