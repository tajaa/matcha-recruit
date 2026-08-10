import XCTest
@testable import Gummfit

final class SafeURLTests: XCTestCase {
    func testAssetURLPassesThroughHTTPSURL() {
        XCTAssertEqual(
            SafeURL.assetURL("https://cdn.example.com/catalog/serum.jpg")?.absoluteString,
            "https://cdn.example.com/catalog/serum.jpg"
        )
    }

    func testAssetURLResolvesRootRelativeStoragePath() {
        let url = SafeURL.assetURL("/uploads/resumes/serum.jpg")

        XCTAssertEqual(url?.path, "/uploads/resumes/serum.jpg")
        XCTAssertNotNil(url?.scheme)
        XCTAssertNotNil(url?.host)
    }

    func testAssetURLRejectsUnsupportedScheme() {
        XCTAssertNil(SafeURL.assetURL("s3://private-bucket/catalog/serum.jpg"))
    }
}
