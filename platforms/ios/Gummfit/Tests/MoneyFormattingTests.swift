import XCTest
@testable import Gummfit

/// `Formatters.cents` parity with the web app's `fmtCents` (client/src/cappe/types.ts),
/// the `Formatters.date(fromTimeString:)`/`timeString(from:)` round-trip backing the
/// Availability/RateRules DatePicker fields, and `Formatters.bookingDateTime` parity
/// with `formatBookingDateTime`/`validTimezone` (client/src/cappe/utils/bookingTime.ts).
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

    func testBookingDateTimeConvertsToBusinessTimezone() {
        // 15:00 UTC == 8:00 AM PDT (UTC-7, Aug is DST)
        XCTAssertEqual(
            Formatters.bookingDateTime("2026-08-10T15:00:00Z", timezone: "America/Los_Angeles"),
            "Mon, Aug 10 · 8:00 AM"
        )
    }

    func testBookingDateTimeFallsBackToUTCWhenTimezoneNil() {
        XCTAssertEqual(
            Formatters.bookingDateTime("2026-08-10T15:00:00Z", timezone: nil),
            "Mon, Aug 10 · 3:00 PM"
        )
    }

    func testBookingDateTimeFallsBackToUTCWhenTimezoneInvalid() {
        XCTAssertEqual(
            Formatters.bookingDateTime("2026-08-10T15:00:00Z", timezone: "Not/A_Zone"),
            "Mon, Aug 10 · 3:00 PM"
        )
    }

    func testBookingDateTimeCrossesDayBoundaryInLocalTimezone() {
        // 03:00 UTC == 8:00 PM previous day in Los Angeles (PDT, UTC-7)
        XCTAssertEqual(
            Formatters.bookingDateTime("2026-08-10T03:00:00Z", timezone: "America/Los_Angeles"),
            "Sun, Aug 9 · 8:00 PM"
        )
    }

    func testBookingDateTimeMalformedStringReturnsRawInput() {
        XCTAssertEqual(Formatters.bookingDateTime("not-a-date", timezone: "UTC"), "not-a-date")
    }
}
