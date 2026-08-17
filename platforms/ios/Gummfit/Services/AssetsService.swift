import Foundation

struct CappeAsset: Codable, Identifiable, Hashable {
    let id: String
    let kind: String
    let url: String
    let prompt: String?
    let aspect: String?
    let image_size: String?
    let created_at: String
}

private struct CappeAssetList: Decodable {
    let assets: [CappeAsset]
}

private struct CappeImageGenerationRequest: Encodable {
    let prompt: String
    let aspect_ratio: String
    let image_size: String?
    let style: String?
    let mood: String?
}

final class AssetsService {
    static let shared = AssetsService()
    private init() {}

    func upload(siteId: String, image: Data, mime: String, filename: String) async throws -> String {
        let response: CappeUploadResponse = try await APIClient.shared.uploadMultipart(
            path: "/sites/\(siteId)/upload",
            data: image,
            mimeType: mime,
            filename: filename
        )
        return response.url
    }

    func generateImage(
        siteId: String,
        prompt: String,
        aspectRatio: String,
        imageSize: String? = nil,
        style: String? = nil,
        mood: String? = nil
    ) async throws -> String {
        let body = CappeImageGenerationRequest(
            prompt: prompt,
            aspect_ratio: aspectRatio,
            image_size: imageSize,
            style: style,
            mood: mood
        )
        let response: CappeUploadResponse = try await APIClient.shared.request(
            method: "POST",
            path: "/sites/\(siteId)/generate-image",
            body: body
        )
        return response.url
    }

    func assets(siteId: String, kind: String? = nil) async throws -> [CappeAsset] {
        var path = "/sites/\(siteId)/assets"
        if let kind, let encoded = kind.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) {
            path += "?kind=\(encoded)"
        }
        let response: CappeAssetList = try await APIClient.shared.request(method: "GET", path: path)
        return response.assets
    }
}
