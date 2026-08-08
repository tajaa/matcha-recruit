import XCTest
@testable import Gummfit

/// `CappeLocationHours` decodes from server JSONB (`list[dict[str, Any]]`,
/// models/bookings.py:65) — unvalidated, so a legacy row can be missing any
/// key. A `keyNotFound` throw here used to fail the whole `hours` array
/// decode, silently blanking every location picker that loaded it.
final class LocationHoursDecodeTests: XCTestCase {
    func testFullRowDecodes() throws {
        let json = """
        {"day": 2, "open": "09:00:00", "close": "17:00:00", "closed": false}
        """
        let hours = try JSONDecoder().decode(CappeLocationHours.self, from: Data(json.utf8))
        XCTAssertEqual(hours.day, 2)
        XCTAssertEqual(hours.open, "09:00:00")
        XCTAssertFalse(hours.closed)
    }

    func testMissingClosedKeyFallsBackToFalse() throws {
        let json = """
        {"day": 0, "open": "09:00:00", "close": "17:00:00"}
        """
        let hours = try JSONDecoder().decode(CappeLocationHours.self, from: Data(json.utf8))
        XCTAssertEqual(hours.day, 0)
        XCTAssertFalse(hours.closed)
    }

    func testEmptyObjectDecodesToDefaults() throws {
        let hours = try JSONDecoder().decode(CappeLocationHours.self, from: Data("{}".utf8))
        XCTAssertEqual(hours.day, 0)
        XCTAssertNil(hours.open)
        XCTAssertNil(hours.close)
        XCTAssertFalse(hours.closed)
    }
}
