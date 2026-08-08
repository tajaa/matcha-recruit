import XCTest
import UIKit
@testable import TellUs

final class MediaPrepareTests: XCTestCase {
    func testSmallJpegPassesThrough() throws {
        let data = try smallJPEGData()
        let prepared = try MediaUploadService.prepare(data: data, mimeType: "image/jpeg", filename: "a.jpg", mediaType: .photo)
        XCTAssertEqual(prepared.data, data)
        XCTAssertEqual(prepared.mimeType, "image/jpeg")
    }

    func testHeicPassesThrough() throws {
        let data = try smallJPEGData() // stand-in bytes; only the mime/size gate is under test
        let prepared = try MediaUploadService.prepare(data: data, mimeType: "image/heic", filename: "a.heic", mediaType: .photo)
        XCTAssertEqual(prepared.mimeType, "image/heic")
    }

    func testOversizePhotoRecompressed() throws {
        // A solid-color PNG compresses far below the 10MB gate regardless of
        // dimensions, so use random noise (near-incompressible) to force a
        // genuinely oversize source and exercise the UIImage decode +
        // downscale + recompress path.
        guard let raw = try noisePNGData(width: 2200, height: 2200) else {
            return XCTFail("couldn't render noise test image")
        }
        XCTAssertGreaterThan(raw.count, 10_000_000, "test fixture must exceed the photo size gate")
        let prepared = try MediaUploadService.prepare(data: raw, mimeType: "image/png", filename: "big.png", mediaType: .photo)
        XCTAssertLessThanOrEqual(prepared.data.count, 10_000_000)
        XCTAssertEqual(prepared.mimeType, "image/jpeg")
    }

    private func noisePNGData(width: Int, height: Int) throws -> Data? {
        var pixels = [UInt8](repeating: 0, count: width * height * 4)
        for i in 0..<pixels.count { pixels[i] = UInt8.random(in: 0...255) }
        let colorSpace = CGColorSpaceCreateDeviceRGB()
        guard let context = CGContext(
            data: &pixels, width: width, height: height, bitsPerComponent: 8,
            bytesPerRow: width * 4, space: colorSpace,
            bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
        ), let cgImage = context.makeImage() else { return nil }
        return UIImage(cgImage: cgImage).pngData()
    }

    func testOversizeVideoThrows() {
        let data = Data(count: 201_000_000)
        XCTAssertThrowsError(try MediaUploadService.prepare(data: data, mimeType: "video/mp4", filename: "big.mp4", mediaType: .video)) { error in
            XCTAssertEqual(error as? MediaError, .videoTooLarge)
        }
    }

    private func smallJPEGData() throws -> Data {
        let image = UIGraphicsImageRenderer(size: CGSize(width: 10, height: 10)).image { ctx in
            UIColor.blue.setFill()
            ctx.fill(CGRect(x: 0, y: 0, width: 10, height: 10))
        }
        guard let data = image.jpegData(compressionQuality: 0.9) else {
            throw NSError(domain: "test", code: 0)
        }
        return data
    }
}

extension MediaError: Equatable {
    public static func == (lhs: MediaError, rhs: MediaError) -> Bool {
        switch (lhs, rhs) {
        case (.photoTooLarge, .photoTooLarge), (.videoTooLarge, .videoTooLarge),
             (.unsupportedType, .unsupportedType):
            return true
        case (.uploadFailed(let a), .uploadFailed(let b)):
            return a == b
        default:
            return false
        }
    }
}
