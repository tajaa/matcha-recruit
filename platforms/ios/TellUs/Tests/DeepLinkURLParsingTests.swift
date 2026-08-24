import XCTest
@testable import TellUs

final class DeepLinkURLParsingTests: XCTestCase {
    func testOfferLinkParsesWithTellUsPath() {
        let route = DeepLinkRoute.parse(url: URL(string: "https://hey-matcha.com/tellus/o/abc123")!)
        XCTAssertEqual(route, .shoutoutOffer(token: "abc123"))
    }

    func testOfferCodeLinkParses() {
        let route = DeepLinkRoute.parse(url: URL(string: "https://www.hey-matcha.com/tellus/o/code/7H2K9PQR")!)
        XCTAssertEqual(route, .shoutoutCode(code: "7H2K9PQR"))
    }

    func testUnrelatedURLIsIgnored() {
        XCTAssertNil(DeepLinkRoute.parse(url: URL(string: "https://hey-matcha.com/tellus/b/store")!))
    }

    func testRejectsNonCanonicalHostsAndAPIPaths() {
        XCTAssertNil(DeepLinkRoute.parse(url: URL(string: "http://hey-matcha.com/tellus/o/abc123")!))
        XCTAssertNil(DeepLinkRoute.parse(url: URL(string: "https://other.example/tellus/o/abc123")!))
        XCTAssertNil(DeepLinkRoute.parse(url: URL(string: "https://hey-matcha.com/api/o/abc123")!))
        XCTAssertNil(DeepLinkRoute.parse(url: URL(string: "https://hey-matcha.com/tellus/o/abc123/extra")!))
    }
}
