import XCTest
@testable import TellUs

final class RedeemCodeNormalizationTests: XCTestCase {
    func testNormalizesWhitespaceAndCase() {
        XCTAssertEqual(normalizeShoutoutCode(" 7h2k9pqr \n"), "7H2K9PQR")
    }

    func testRejectsIncorrectLengthAndExcludedCharacters() {
        XCTAssertNil(normalizeShoutoutCode("7H2K9PQ"))
        XCTAssertNil(normalizeShoutoutCode("7H2K9PQRR"))
        XCTAssertNil(normalizeShoutoutCode("7H2K9PIR"))
        XCTAssertNil(normalizeShoutoutCode("7H2K-9PQ"))
    }
}
