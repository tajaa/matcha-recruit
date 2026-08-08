import UIKit

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
/// 5MB, jpeg/png/gif/webp only — no SVG, stored-XSS guard). Passthrough when
/// already under the cap in an allowed format; otherwise downscale + re-encode
/// as JPEG until it fits, matching the plan's "still-over throws" contract.
enum ImagePrep {
    static let maxBytes = 5 * 1024 * 1024
    private static let allowedMimeTypes: Set<String> = ["image/jpeg", "image/png", "image/gif", "image/webp"]
    private static let minScale: CGFloat = 0.2

    struct Prepared {
        let data: Data
        let mimeType: String
        let filename: String
    }

    static func prepare(data: Data, mimeType: String, filename: String) throws -> Prepared {
        if allowedMimeTypes.contains(mimeType) && data.count <= maxBytes {
            return Prepared(data: data, mimeType: mimeType, filename: filename)
        }
        guard let image = UIImage(data: data) else { throw ImagePrepError.unsupportedFormat }

        var scale: CGFloat = 1.0
        var jpeg = image.jpegData(compressionQuality: 0.8)
        while let current = jpeg, current.count > maxBytes, scale > minScale {
            scale -= 0.2
            let newSize = CGSize(width: image.size.width * scale, height: image.size.height * scale)
            let renderer = UIGraphicsImageRenderer(size: newSize)
            let resized = renderer.image { _ in image.draw(in: CGRect(origin: .zero, size: newSize)) }
            jpeg = resized.jpegData(compressionQuality: 0.8)
        }
        guard let final = jpeg, final.count <= maxBytes else { throw ImagePrepError.tooLarge }
        let jpgName = (filename as NSString).deletingPathExtension + ".jpg"
        return Prepared(data: final, mimeType: "image/jpeg", filename: jpgName)
    }
}
