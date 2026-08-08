import XCTest
@testable import Gummfit

/// `Clearable` fixes a real bug: Swift's synthesized `Encodable` skips `nil`
/// Optionals outright, so a PATCH could never clear a nullable server column
/// (the server's `build_patch` keys off `model_fields_set` — an explicit
/// JSON `null` clears, an absent key leaves untouched). These tests assert
/// the wire shape directly rather than the Swift value, since that's the
/// distinction the server actually observes.
final class ClearablePatchTests: XCTestCase {
    private func decodeJSON(_ body: some Encodable) throws -> [String: Any] {
        let data = try JSONEncoder().encode(body)
        return try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
    }

    func testProductUpdateUnsetFieldIsOmittedFromWire() throws {
        let json = try decodeJSON(CappeProductUpdate(name: "Latte"))
        XCTAssertNil(json["description"])
        XCTAssertNil(json["image_url"])
        XCTAssertNil(json["sku"])
        XCTAssertNil(json["inventory"])
        XCTAssertEqual(json["name"] as? String, "Latte")
    }

    func testProductUpdateClearedFieldSendsExplicitNull() throws {
        let json = try decodeJSON(CappeProductUpdate(name: "Latte", description: .clear, sku: .clear))
        // NSNull is how JSONSerialization represents a JSON `null` that was
        // actually present in the payload — distinct from the key being
        // absent (which reads back as a plain missing dictionary entry).
        XCTAssertTrue(json["description"] is NSNull)
        XCTAssertTrue(json["sku"] is NSNull)
    }

    func testProductUpdateValueFieldSendsTheValue() throws {
        let json = try decodeJSON(CappeProductUpdate(name: "Latte", description: .value("Oat milk latte"), inventory: .value(12)))
        XCTAssertEqual(json["description"] as? String, "Oat milk latte")
        XCTAssertEqual(json["inventory"] as? Int, 12)
    }

    func testOrderStatusUpdateStatusNeverGoesClearable() throws {
        // Only carrier/tracking_number are Clearable — status must remain a
        // plain optional since the server rejects an explicit-null status
        // (CappeOrderStatusUpdate._validate_fields, models/shop.py:216-223).
        let json = try decodeJSON(CappeOrderStatusUpdate(status: "paid"))
        XCTAssertEqual(json["status"] as? String, "paid")
        XCTAssertNil(json["carrier"])
        XCTAssertNil(json["tracking_number"])
    }

    func testOrderStatusUpdateClearsTracking() throws {
        let json = try decodeJSON(CappeOrderStatusUpdate(status: nil, carrier: .unset, tracking_number: .clear))
        XCTAssertNil(json["status"])
        XCTAssertNil(json["carrier"])
        XCTAssertTrue(json["tracking_number"] is NSNull)
    }

    func testClearableFromBuildsUnsetWhenNotTouched() {
        let result: Clearable<String> = .from("anything", touched: false)
        XCTAssertFalse(result.isPresent)
    }

    func testClearableFromBuildsClearForEmptiedTouchedField() {
        let result: Clearable<String> = .from("", touched: true)
        if case .clear = result {} else { XCTFail("expected .clear") }
    }

    func testClearableFromBuildsValueForNonEmptyTouchedField() {
        let result: Clearable<String> = .from("UPS", touched: true)
        if case .value(let v) = result { XCTAssertEqual(v, "UPS") } else { XCTFail("expected .value") }
    }
}
