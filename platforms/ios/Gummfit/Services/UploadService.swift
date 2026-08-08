import Foundation

/// Multipart image upload — product photos, site logos, etc. Callers run
/// `ImagePrep.prepare` first; this just wraps the endpoint call.
final class UploadService {
    static let shared = UploadService()
    private init() {}

    func uploadImage(siteId: String, prepared: ImagePrep.Prepared) async throws -> CappeUploadResponse {
        try await APIClient.shared.uploadMultipart(
            path: "/sites/\(siteId)/upload",
            data: prepared.data,
            mimeType: prepared.mimeType,
            filename: prepared.filename
        )
    }
}
