import XCTest
@testable import Gummfit

/// `Formatters.cents` parity with the web app's `fmtCents` (client/src/cappe/types.ts)
/// plus the `Formatters.date(fromTimeString:)`/`timeString(from:)` round-trip
/// backing the Availability/RateRules DatePicker fields.
final class MoneyFormattingTests: XCTestCase {
    func testNilCentsFormatsAsZero() {
        XCTAssertEqual(Formatters.cents(nil), "$0.00")
    }

    func testWholeDollarAmount() {
        XCTAssertEqual(Formatters.cents(1000), "$10.00")
    }

    func testFractionalCentsRoundTrip() {
        XCTAssertEqual(Formatters.cents(1099), "$10.99")
    }

    func testZeroCents() {
        XCTAssertEqual(Formatters.cents(0), "$0.00")
    }

    func testNonUSDCurrencyUsesItsOwnSymbol() {
        XCTAssertEqual(Formatters.cents(1000, currency: "EUR"), "€10.00")
    }

    func testTimeStringRoundTrip() {
        let date = Formatters.date(fromTimeString: "17:30:00")
        XCTAssertEqual(Formatters.timeString(from: date), "17:30:00")
    }

    func testTimeStringRoundTripMidnight() {
        let date = Formatters.date(fromTimeString: "00:00:00")
        XCTAssertEqual(Formatters.timeString(from: date), "00:00:00")
    }
}
