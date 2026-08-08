import XCTest
@testable import Gummfit

/// `OrderDetailViewModel.isValidStatusUpdate` mirrors the server's
/// `CappeOrderStatusUpdate.model_validator` (server/app/cappe/models/shop.py:216-223)
/// — at least one of status/carrier/tracking_number must be present.
final class OrderStatusUpdateTests: XCTestCase {
    func testAllUnsetIsInvalid() {
        XCTAssertFalse(OrderDetailViewModel.isValidStatusUpdate(status: nil, carrier: .unset, trackingNumber: .unset))
    }

    func testStatusOnlyIsValid() {
        XCTAssertTrue(OrderDetailViewModel.isValidStatusUpdate(status: "paid", carrier: .unset, trackingNumber: .unset))
    }

    func testCarrierOnlyIsValid() {
        XCTAssertTrue(OrderDetailViewModel.isValidStatusUpdate(status: nil, carrier: .value("UPS"), trackingNumber: .unset))
    }

    func testTrackingOnlyIsValid() {
        XCTAssertTrue(OrderDetailViewModel.isValidStatusUpdate(status: nil, carrier: .unset, trackingNumber: .value("1Z999")))
    }

    /// A cleared (not just changed) field still counts as "present" — the
    /// user explicitly emptied it, which is a real PATCH, not a no-op.
    func testClearedCarrierIsValid() {
        XCTAssertTrue(OrderDetailViewModel.isValidStatusUpdate(status: nil, carrier: .clear, trackingNumber: .unset))
    }
}
