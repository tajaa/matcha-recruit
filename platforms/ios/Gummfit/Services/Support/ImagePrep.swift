import UIKit
import ImageIO
import UniformTypeIdentifiers

enum ImagePrepError: Error, LocalizedError {
    case unsupportedFormat
    case tooLarge

    var errorDescription: String? {
        switch self {
        case .unsupportedFormat: return "Unsupported image format."
        case .tooLarge: return "Image is too large even after compression."
        }
    }
}

/// Prepares a PhotosPicker-selected image for `APIClient.uploadMultipart`,
/// mirroring the server's cap (server/app/cappe/routes/uploads.py:38-45:
/// 5MB, jpeg/png/gif/webp only — no SVG, stored-XSS guard). Under-cap allowed
/// formats get their metadata stripped (never uploaded verbatim — see
/// `strippingMetadata`); everything else is downscaled + re-encoded until it
/// fits, matching the plan's "still-over throws" contract.
enum ImagePrep {
    static let maxBytes = 5 * 1024 * 1024
    private static let allowedMimeTypes: Set<String> = ["image/jpeg", "image/png", "image/gif", "image/webp"]
    /// Fixed ladder rather than `scale -= 0.2` in a loop — float accumulation
    /// there (0.8, 0.6000000000000001, …) let the loop run one extra pass at
    /// scale ≈ 1.2e-16, producing a degenerate near-zero-pixel image.
    private static let scaleSteps: [CGFloat] = [0.8, 0.6, 0.4, 0.2]

    struct Prepared {
        let data: Data
        let mimeType: String
        let filename: String
    }

    static func prepare(data: Data, mimeType: String, filename: String) throws -> Prepared {
        if allowedMimeTypes.contains(mimeType) && data.count <= maxBytes,
           let stripped = strippingMetadata(data), stripped.count <= maxBytes {
            return Prepared(data: stripped, mimeType: mimeType, filename: filename)
        }
        guard let image = UIImage(data: data) else { throw ImagePrepError.unsupportedFormat }

        let alpha = hasAlpha(image)
        let format = UIGraphicsImageRendererFormat.default()
        format.scale = 1  // pin to 1x — the renderer otherwise defaults to the
                           // screen scale (often 3x), which can INCREASE pixel
                           // count even while "downscaling" by a fraction < 1.
        format.opaque = !alpha

        func encode(_ img: UIImage) -> Data? {
            alpha ? img.pngData() : img.jpegData(compressionQuality: 0.8)
        }

        var encoded = encode(image)
        for step in scaleSteps {
            guard let current = encoded, current.count > maxBytes else { break }
            let newSize = CGSize(
                width: max(1, (image.size.width * step).rounded()),
                height: max(1, (image.size.height * step).rounded())
            )
            let renderer = UIGraphicsImageRenderer(size: newSize, format: format)
            let resized = renderer.image { _ in image.draw(in: CGRect(origin: .zero, size: newSize)) }
            encoded = encode(resized)
        }
        guard let final = encoded, final.count <= maxBytes else { throw ImagePrepError.tooLarge }
        let ext = alpha ? "png" : "jpg"
        let mime = alpha ? "image/png" : "image/jpeg"
        let outName = (filename as NSString).deletingPathExtension + "." + ext
        return Prepared(data: final, mimeType: mime, filename: outName)
    }

    private static func hasAlpha(_ image: UIImage) -> Bool {
        switch image.cgImage?.alphaInfo {
        case .first, .last, .premultipliedFirst, .premultipliedLast:
            return true
        default:
            return false
        }
    }

    /// Drops GPS / EXIF / TIFF / IPTC / Apple-maker metadata while preserving
    /// the original encoding (and therefore alpha) — passthrough must never
    /// republish a photo's location to the public CDN URL the server hands
    /// back. Orientation is carried across explicitly since it lives in the
    /// TIFF dict being removed; losing it renders portrait photos sideways.
    /// Returns nil if the source isn't decodable as image data.
    private static func strippingMetadata(_ data: Data) -> Data? {
        guard let source = CGImageSourceCreateWithData(data as CFData, nil),
              CGImageSourceGetCount(source) > 0,
              let type = CGImageSourceGetType(source) else { return nil }
        let props = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any]
        let output = NSMutableData()
        guard let dest = CGImageDestinationCreateWithData(output, type, 1, nil) else { return nil }

        var removals: [CFString: Any] = [
            kCGImagePropertyGPSDictionary: kCFNull as Any,
            kCGImagePropertyExifDictionary: kCFNull as Any,
            kCGImagePropertyExifAuxDictionary: kCFNull as Any,
            kCGImagePropertyTIFFDictionary: kCFNull as Any,
            kCGImagePropertyIPTCDictionary: kCFNull as Any,
            kCGImagePropertyMakerAppleDictionary: kCFNull as Any,
        ]
        if let orientation = props?[kCGImagePropertyOrientation] {
            removals[kCGImagePropertyOrientation] = orientation
        }

        CGImageDestinationAddImageFromSource(dest, source, 0, removals as CFDictionary)
        guard CGImageDestinationFinalize(dest) else { return nil }
        return output as Data
    }
}
