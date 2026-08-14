import UIKit
import XCTest
@testable import TellUs

final class FlyerExportTests: XCTestCase {
    func testExportDimensionsMatchArtboardAtBothDPIValues() throws {
        var design = FlyerDesignFactory.blank()
        design.layers = [FlyerDesignFactory.qr(in: design)]
        let directory = FileManager.default.temporaryDirectory

        let image150URL = try FlyerExportService.writePNG(
            design: design,
            claimURL: "https://example.com/promo/claim",
            assets: .bundled,
            dpi: .dpi150,
            directory: directory
        )
        let image300URL = try FlyerExportService.writePNG(
            design: design,
            claimURL: "https://example.com/promo/claim",
            assets: .bundled,
            dpi: .dpi300,
            directory: directory
        )
        defer {
            try? FileManager.default.removeItem(at: image150URL)
            try? FileManager.default.removeItem(at: image300URL)
        }

        let image150 = try XCTUnwrap(UIImage(contentsOfFile: image150URL.path))
        let image300 = try XCTUnwrap(UIImage(contentsOfFile: image300URL.path))
        XCTAssertEqual(image150.size.width, 1275, accuracy: 0.01)
        XCTAssertEqual(image150.size.height, 1650, accuracy: 0.01)
        XCTAssertEqual(image300.size.width, 2550, accuracy: 0.01)
        XCTAssertEqual(image300.size.height, 3300, accuracy: 0.01)
        XCTAssertTrue(try Data(contentsOf: image150URL).starts(with: [0x89, 0x50, 0x4E, 0x47]))
    }

    func testExportRequiresClaimURL() {
        XCTAssertThrowsError(try FlyerExportService.writePNG(
            design: FlyerDesignFactory.blank(),
            claimURL: "",
            assets: .bundled,
            dpi: .dpi150
        )) { error in
            XCTAssertEqual(error as? FlyerExportError, .missingClaimURL)
        }
    }
}
