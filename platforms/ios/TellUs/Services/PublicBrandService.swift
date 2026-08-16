import Foundation

/// Narrow public business-page client used by native Comms. The full review
/// page remains a web handoff; native only needs the messaging flag and store
/// choices before starting a conversation.
final class PublicBrandService {
    static let shared = PublicBrandService()
    private let client = APIClient.shared
    private init() {}

    func brand(slug: String) async throws -> PublicBrandPage {
        try await client.request(method: "GET", path: "/b/\(slug)")
    }

    /// Same endpoint as `brand(slug:)`, decoded into the fuller
    /// TellusPublicBrandPage shape BrandDetailView needs (reviews, rating,
    /// follow/board state) — the narrow PublicBrandPage above only carries
    /// what native Comms needs before starting a conversation.
    func brandDetail(slug: String) async throws -> TellusPublicBrandPage {
        try await client.request(method: "GET", path: "/b/\(slug)")
    }
}
