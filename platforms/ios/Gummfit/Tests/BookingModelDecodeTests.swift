import XCTest
@testable import Gummfit

/// Pins CappeBooking/CappeBookingType/CappeAvailability decode against real
/// server response shapes (server/app/cappe/models/bookings.py).
final class BookingModelDecodeTests: XCTestCase {
    func testBookingTypeDecodesWithStaffIds() throws {
        let json = """
        {
          "id": "type-1", "site_id": "site-1", "name": "Haircut", "description": null,
          "duration_minutes": 30, "price_cents": 3000, "status": "active",
          "requires_approval": false, "pricing_mode": "flat", "category": null,
          "buffer_minutes": 5, "staff_ids": ["staff-1", "staff-2"], "location_id": null,
          "created_at": "2026-08-01T00:00:00Z", "updated_at": "2026-08-01T00:00:00Z"
        }
        """
        let type = try JSONDecoder().decode(CappeBookingType.self, from: Data(json.utf8))
        XCTAssertEqual(type.staff_ids, ["staff-1", "staff-2"])
        XCTAssertEqual(type.duration_minutes, 30)
    }

    func testAvailabilityDecodes() throws {
        let json = """
        {"id": "avail-1", "weekday": 2, "start_time": "09:00:00", "end_time": "17:00:00",
         "booking_type_id": null, "staff_id": null, "location_id": null}
        """
        let slot = try JSONDecoder().decode(CappeAvailability.self, from: Data(json.utf8))
        XCTAssertEqual(slot.weekday, 2)
        XCTAssertEqual(slot.start_time, "09:00:00")
    }

    func testBookingDecodesWithStatus() throws {
        let json = """
        {
          "id": "booking-1", "site_id": "site-1", "booking_type_id": "type-1", "staff_id": null,
          "staff_name": null, "location_id": null, "location_name": null,
          "customer_name": "Jane Doe", "customer_email": "jane@example.com",
          "starts_at": "2026-08-10T15:00:00Z", "ends_at": "2026-08-10T15:30:00Z",
          "status": "confirmed", "note": null, "requires_approval": false,
          "quoted_price_cents": 3000, "approved_at": null, "decline_reason": null,
          "rider_acknowledged": false, "created_at": "2026-08-01T00:00:00Z"
        }
        """
        let booking = try JSONDecoder().decode(CappeBooking.self, from: Data(json.utf8))
        XCTAssertEqual(booking.status, .confirmed)
        XCTAssertEqual(booking.quoted_price_cents, 3000)
    }

    func testUnknownBookingStatusFallsBackNotThrows() throws {
        let decoded = try JSONDecoder().decode(BookingStatus.self, from: Data("\"no_show\"".utf8))
        XCTAssertEqual(decoded, .unknown)
    }
}
