import XCTest
@testable import TellUs

final class IntakeTokenTests: XCTestCase {
    func testFullWebURL() {
        XCTAssertEqual(intakeToken(from: "https://hey-matcha.com/tellus/i/abc12345"), "abc12345")
    }

    func testPathOnly() {
        XCTAssertEqual(intakeToken(from: "/i/abc12345"), "abc12345")
    }

    func testBareToken() {
        XCTAssertEqual(intakeToken(from: "abc123XY_-"), "abc123XY_-")
    }

    func testRejectsShort() {
        XCTAssertNil(intakeToken(from: "abc"))
    }

    func testRejectsGarbage() {
        XCTAssertNil(intakeToken(from: "hello world"))
    }

    func testTrailingSlash() {
        XCTAssertEqual(intakeToken(from: "https://hey-matcha.com/tellus/i/abc12345/"), "abc12345")
    }
}
