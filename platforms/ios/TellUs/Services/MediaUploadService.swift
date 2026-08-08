import Foundation
import UIKit
import UniformTypeIdentifiers

enum MediaError: Error, LocalizedError {
    case photoTooLarge
    case videoTooLarge
    case unsupportedType
    case uploadFailed(Int)

    var errorDescription: String? {
        switch self {
        case .photoTooLarge: return "Photo too large even after compression (max 10 MB)."
        case .videoTooLarge: return "Video too large (max 200 MB)."
        case .unsupportedType: return "Unsupported file type."
        case .uploadFailed(let code): return "Upload failed (HTTP \(code))."
        }
    }
}

struct PreparedUpload {
    let data: Data
    let mimeType: String
    let filename: String
    let mediaType: MediaType
}

final class MediaUploadService {
    static let shared = MediaUploadService()
    private let intake = IntakeService.shared
    private init() {}

    private static let photoLimit = 10_000_000
    private static let videoLimit = 200_000_000
    private static let passthroughPhotoMimes: Set<String> = [
        "image/jpeg", "image/png", "image/webp", "image/gif", "image/heic", "image/heif",
    ]
    private static let passthroughVideoMimes: Set<String> = [
        "video/mp4", "video/webm", "video/quicktime",
    ]

    /// Photo: HEIC/HEIF/JPEG/PNG/WebP/GIF pass through untouched if ≤10MB
    /// (server accepts all of these). Oversize → recompress as JPEG at 0.8
    /// quality, downscaling the long edge to ≤4032px if still too big.
    /// Video: mp4/webm/quicktime pass through if ≤200MB; anything else throws.
    static func prepare(data: Data, mimeType: String, filename: String, mediaType: MediaType) throws -> PreparedUpload {
        switch mediaType {
        case .photo:
            if passthroughPhotoMimes.contains(mimeType) && data.count <= photoLimit {
                return PreparedUpload(data: data, mimeType: mimeType, filename: filename, mediaType: .photo)
            }
            guard let image = UIImage(data: data) else { throw MediaError.unsupportedType }
            var working = image
            let maxEdge: CGFloat = 4032
            if max(image.size.width, image.size.height) > maxEdge {
                let scale = maxEdge / max(image.size.width, image.size.height)
                let newSize = CGSize(width: image.size.width * scale, height: image.size.height * scale)
                let renderer = UIGraphicsImageRenderer(size: newSize)
                working = renderer.image { _ in image.draw(in: CGRect(origin: .zero, size: newSize)) }
            }
            guard let jpeg = working.jpegData(compressionQuality: 0.8), jpeg.count <= photoLimit else {
                throw MediaError.photoTooLarge
            }
            let newName = (filename as NSString).deletingPathExtension + ".jpg"
            return PreparedUpload(data: jpeg, mimeType: "image/jpeg", filename: newName, mediaType: .photo)
        case .video:
            guard passthroughVideoMimes.contains(mimeType) else { throw MediaError.unsupportedType }
            guard data.count <= videoLimit else { throw MediaError.videoTooLarge }
            return PreparedUpload(data: data, mimeType: mimeType, filename: filename, mediaType: .video)
        }
    }

    /// 1. presign  2. raw PUT to S3 (no auth header, no APIClient retry
    /// policy — S3 signature covers exactly the presigned headers)
    /// 3. return the SubmittedMedia the intake submit body expects.
    func upload(token: String, prepared: PreparedUpload) async throws -> SubmittedMedia {
        let presign = try await intake.presign(token: token, MediaPresignRequest(
            media_type: prepared.mediaType.rawValue,
            mime_type: prepared.mimeType,
            file_size: prepared.data.count,
            original_filename: prepared.filename
        ))
        guard let url = URL(string: presign.upload_url) else { throw APIError.invalidURL }
        var req = URLRequest(url: url)
        req.httpMethod = "PUT"
        req.setValue(prepared.mimeType, forHTTPHeaderField: "Content-Type")
        let (_, response) = try await URLSession.shared.upload(for: req, from: prepared.data)
        guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
            throw MediaError.uploadFailed((response as? HTTPURLResponse)?.statusCode ?? 0)
        }
        return SubmittedMedia(
            storage_path: presign.storage_path,
            media_type: prepared.mediaType.rawValue,
            mime_type: prepared.mimeType,
            file_size: prepared.data.count,
            original_filename: prepared.filename
        )
    }
}
