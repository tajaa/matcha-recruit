import XCTest
import ImageIO
import UniformTypeIdentifiers
@testable import Gummfit

final class ImagePrepTests: XCTestCase {
    func testPassthroughUnderCapAllowedFormat() throws {
        let image = Self.makeImage(size: CGSize(width: 40, height: 40))
        let data = image.pngData()!
        let prepared = try ImagePrep.prepare(data: data, mimeType: "image/png", filename: "logo.png")
        XCTAssertEqual(prepared.mimeType, "image/png")
        XCTAssertEqual(prepared.filename, "logo.png")
        let decoded = UIImage(data: prepared.data)
        XCTAssertEqual(decoded?.size, image.size)
    }

    func testStripsGPSMetadata() throws {
        let tagged = Self.makeJPEG(size: CGSize(width: 40, height: 40), gps: true)
        let prepared = try ImagePrep.prepare(data: tagged, mimeType: "image/jpeg", filename: "photo.jpg")
        let props = Self.properties(of: prepared.data)
        XCTAssertNil(props?[kCGImagePropertyGPSDictionary])
    }

    func testPreservesOrientation() throws {
        let tagged = Self.makeJPEG(size: CGSize(width: 40, height: 40), orientation: 6)
        let prepared = try ImagePrep.prepare(data: tagged, mimeType: "image/jpeg", filename: "photo.jpg")
        let props = Self.properties(of: prepared.data)
        XCTAssertEqual(props?[kCGImagePropertyOrientation] as? Int, 6)
    }

    func testTransparentPNGKeepsAlpha() throws {
        let image = Self.makeImage(size: CGSize(width: 2000, height: 2000), transparent: true)
        let data = image.pngData()!
        // Force the re-encode path regardless of the raw PNG's size.
        let prepared = try ImagePrep.prepare(data: data, mimeType: "image/heic", filename: "logo.heic")
        XCTAssertEqual(prepared.mimeType, "image/png")
        XCTAssertEqual(prepared.filename, "logo.png")
        let decoded = UIImage(data: prepared.data)
        XCTAssertNotNil(decoded)
        switch decoded?.cgImage?.alphaInfo {
        case .first, .last, .premultipliedFirst, .premultipliedLast:
            break
        default:
            XCTFail("expected alpha to survive re-encode")
        }
    }

    func testOversizeImageDownscalesWithinCap() throws {
        // A flat-color PNG compresses too well to land over the cap on its
        // own, so force the re-encode path via a disallowed mime — that's
        // what actually exercises the scale ladder.
        let image = Self.makeImage(size: CGSize(width: 6000, height: 6000))
        let data = image.pngData()!
        let prepared = try ImagePrep.prepare(data: data, mimeType: "image/heic", filename: "big.heic")
        XCTAssertLessThanOrEqual(prepared.data.count, ImagePrep.maxBytes)
        let decoded = UIImage(data: prepared.data)
        XCTAssertNotNil(decoded)
        XCTAssertGreaterThan(decoded?.size.width ?? 0, 0)
        XCTAssertGreaterThan(decoded?.size.height ?? 0, 0)
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

    private static func makeImage(size: CGSize, transparent: Bool = false) -> UIImage {
        // Pin scale to 1 (points == pixels) and opacity to the intent —
        // UIGraphicsImageRenderer's default format is non-opaque regardless
        // of what's drawn, which would make every synthetic image here
        // falsely report an alpha channel to `ImagePrep.hasAlpha`.
        let format = UIGraphicsImageRendererFormat.default()
        format.scale = 1
        format.opaque = !transparent
        let renderer = UIGraphicsImageRenderer(size: size, format: format)
        return renderer.image { ctx in
            UIColor.red.withAlphaComponent(transparent ? 0.3 : 1.0).setFill()
            ctx.fill(CGRect(origin: .zero, size: size))
        }
    }

    private static func makeJPEG(size: CGSize, gps: Bool = false, orientation: Int? = nil) -> Data {
        let image = makeImage(size: size)
        let jpeg = image.jpegData(compressionQuality: 0.9)!
        guard let source = CGImageSourceCreateWithData(jpeg as CFData, nil) else { return jpeg }
        let output = NSMutableData()
        guard let dest = CGImageDestinationCreateWithData(output, UTType.jpeg.identifier as CFString, 1, nil) else { return jpeg }
        var props: [CFString: Any] = [:]
        if gps {
            props[kCGImagePropertyGPSDictionary] = [kCGImagePropertyGPSLatitude: 37.0, kCGImagePropertyGPSLongitude: -122.0]
        }
        if let orientation {
            props[kCGImagePropertyOrientation] = orientation
        }
        CGImageDestinationAddImageFromSource(dest, source, 0, props as CFDictionary)
        CGImageDestinationFinalize(dest)
        return output as Data
    }

    private static func properties(of data: Data) -> [CFString: Any]? {
        guard let source = CGImageSourceCreateWithData(data as CFData, nil) else { return nil }
        return CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any]
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
