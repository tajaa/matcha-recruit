import XCTest
@testable import TellUs

final class ResetTokenTests: XCTestCase {
    func testFullWebURL() {
        let token = resetToken(from: "https://hey-matcha.com/tellus/reset-password?token=abcdef0123456789")
        XCTAssertEqual(token, "abcdef0123456789")
    }

    func testBareToken() {
        XCTAssertEqual(resetToken(from: "abcdef0123456789"), "abcdef0123456789")
    }

    func testRejectsShort() {
        XCTAssertNil(resetToken(from: "short"))
    }

    func testRejectsGarbage() {
        XCTAssertNil(resetToken(from: "hello world this is not a token"))
    }
}
