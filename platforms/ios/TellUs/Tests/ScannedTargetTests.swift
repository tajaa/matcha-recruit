import XCTest
@testable import TellUs

/// One camera reads two kinds of QR in the wild — a feedback-intake link on a
/// table tent and a promo claim link on a flyer — so telling them apart is the
/// whole job here. Getting it wrong sends someone to a feedback form when they
/// scanned a free-coffee flyer.
final class ScannedTargetTests: XCTestCase {
    func testPromoClaimFullURL() {
        XCTAssertEqual(scannedTarget(from: "https://hey-matcha.com/tellus/p/abc12345"), .promoClaim("abc12345"))
    }

    func testPromoClaimPathOnly() {
        XCTAssertEqual(scannedTarget(from: "/p/abc12345"), .promoClaim("abc12345"))
    }

    func testPromoClaimTrailingSlash() {
        XCTAssertEqual(scannedTarget(from: "https://hey-matcha.com/tellus/p/abc12345/"), .promoClaim("abc12345"))
    }

    func testIntakeStillWins() {
        XCTAssertEqual(scannedTarget(from: "https://hey-matcha.com/tellus/i/abc12345"), .intake("abc12345"))
    }

    /// A bare token has no path to disambiguate it. Intake is the only kind
    /// ever printed without a URL around it, so that stays the reading.
    func testBareTokenIsIntake() {
        XCTAssertEqual(scannedTarget(from: "abc123XY_-"), .intake("abc123XY_-"))
    }

    func testGarbageIsNil() {
        XCTAssertNil(scannedTarget(from: "hello world"))
        XCTAssertNil(scannedTarget(from: "abc"))
    }

    func testIntakeTokenShorthandIgnoresPromoLinks() {
        // The shorthand is still used by the places flow, which must never
        // hand a promo token to the intake loader.
        XCTAssertNil(intakeToken(from: "https://hey-matcha.com/tellus/p/abc12345"))
        XCTAssertEqual(intakeToken(from: "https://hey-matcha.com/tellus/i/abc12345"), "abc12345")
    }
}
