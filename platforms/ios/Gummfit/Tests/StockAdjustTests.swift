import XCTest
@testable import Gummfit

/// `StockAdjustViewModel.preview` is a pure function — mirrors the server's
/// clamp-at-zero on the stored inventory column (models/shop.py:120).
final class StockAdjustTests: XCTestCase {
    func testPositiveDeltaAdds() {
        XCTAssertEqual(StockAdjustViewModel.preview(current: 10, delta: 5), 15)
    }

    func testNegativeDeltaSubtracts() {
        XCTAssertEqual(StockAdjustViewModel.preview(current: 10, delta: -3), 7)
    }

    func testDeltaBelowZeroClampsAtZero() {
        XCTAssertEqual(StockAdjustViewModel.preview(current: 2, delta: -10), 0)
    }

    func testZeroDeltaIsNoOp() {
        XCTAssertEqual(StockAdjustViewModel.preview(current: 5, delta: 0), 5)
    }

    /// `option_id` must be genuinely absent (not `null`) when adjusting the
    /// product's own stock rather than a variant's — the server branches on
    /// `body.option_id is not None` (routes/shop.py:279).
    func testEncodeOmitsOptionIdWhenNil() throws {
        let body = CappeStockAdjust(delta: 3, option_id: nil, reason: "manual", note: nil)
        let data = try JSONEncoder().encode(body)
        let json = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        XCTAssertNil(json["option_id"])
        XCTAssertEqual(json["delta"] as? Int, 3)
    }

    func testEncodeIncludesOptionIdWhenSet() throws {
        let body = CappeStockAdjust(delta: -2, option_id: "opt-1", reason: "damage", note: "dropped")
        let data = try JSONEncoder().encode(body)
        let json = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        XCTAssertEqual(json["option_id"] as? String, "opt-1")
    }
}
