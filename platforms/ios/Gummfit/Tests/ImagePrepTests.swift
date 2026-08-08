import XCTest
@testable import Gummfit

final class ImagePrepTests: XCTestCase {
    func testPassthroughUnderCapAllowedFormat() throws {
        let data = Data(repeating: 0xAB, count: 100)
        let prepared = try ImagePrep.prepare(data: data, mimeType: "image/png", filename: "logo.png")
        XCTAssertEqual(prepared.data, data)
        XCTAssertEqual(prepared.mimeType, "image/png")
        XCTAssertEqual(prepared.filename, "logo.png")
    }

    func testDisallowedFormatUnderCapStillReencodes() throws {
        let image = Self.makeImage(size: CGSize(width: 40, height: 40))
        let heicLikeData = image.pngData()! // stand-in for a format not in the allowlist
        let prepared = try ImagePrep.prepare(data: heicLikeData, mimeType: "image/heic", filename: "photo.heic")
        XCTAssertEqual(prepared.mimeType, "image/jpeg")
        XCTAssertEqual(prepared.filename, "photo.jpg")
        XCTAssertLessThanOrEqual(prepared.data.count, ImagePrep.maxBytes)
    }

    func testGarbageDataThrowsUnsupportedFormat() {
        let garbage = Data([0x00, 0x01, 0x02])
        XCTAssertThrowsError(try ImagePrep.prepare(data: garbage, mimeType: "image/heic", filename: "x.heic")) { error in
            XCTAssertEqual(error as? ImagePrepError, .unsupportedFormat)
        }
    }

    private static func makeImage(size: CGSize) -> UIImage {
        let renderer = UIGraphicsImageRenderer(size: size)
        return renderer.image { ctx in
            UIColor.red.setFill()
            ctx.fill(CGRect(origin: .zero, size: size))
        }
    }
}

extension ImagePrepError: Equatable {
    public static func == (lhs: ImagePrepError, rhs: ImagePrepError) -> Bool {
        switch (lhs, rhs) {
        case (.unsupportedFormat, .unsupportedFormat), (.tooLarge, .tooLarge): return true
        default: return false
        }
    }
}
