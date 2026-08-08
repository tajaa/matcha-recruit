import Foundation

/// Brand-side admin surface: brand identity, prompts, stores, feedback
/// links, and listings CRUD (routes/links.py, prompts.py, marketplace.py).
final class BrandAdminService {
    static let shared = BrandAdminService()
    private let client = APIClient.shared
    private init() {}

    // MARK: - Brand identity

    func brand() async throws -> Brand {
        try await client.request(method: "GET", path: "/brand")
    }

    func updateBrand(_ patch: BrandUpdate) async throws -> Brand {
        try await client.request(method: "PATCH", path: "/brand", body: patch)
    }

    func uploadLogo(data: Data, mimeType: String, filename: String) async throws -> Brand {
        try await client.uploadMultipart(path: "/brand/logo", data: data, mimeType: mimeType, filename: filename)
    }

    func deleteLogo() async throws -> Brand {
        try await client.request(method: "DELETE", path: "/brand/logo")
    }

    // MARK: - Prompts

    func prompts() async throws -> [BrandPrompt] {
        try await client.request(method: "GET", path: "/brand/prompts")
    }

    /// PUT replaces the whole set — array order becomes `position`.
    func setPrompts(_ texts: [String]) async throws -> [BrandPrompt] {
        try await client.request(
            method: "PUT", path: "/brand/prompts",
            body: BrandPromptsUpdate(prompts: texts.map { BrandPromptsUpdate.Item(prompt: $0) })
        )
    }

    // MARK: - Stores

    func stores() async throws -> [Store] {
        try await client.request(method: "GET", path: "/stores")
    }

    func createStore(_ body: StoreCreate) async throws -> Store {
        try await client.request(method: "POST", path: "/stores", body: body)
    }

    func updateStore(id: String, _ body: StoreUpdate) async throws -> Store {
        try await client.request(method: "PATCH", path: "/stores/\(id)", body: body)
    }

    func deleteStore(id: String) async throws {
        try await client.requestVoid(method: "DELETE", path: "/stores/\(id)")
    }

    // MARK: - Feedback links (QR)

    func links() async throws -> [FeedbackLink] {
        try await client.request(method: "GET", path: "/links")
    }

    func createLink(_ body: LinkCreate) async throws -> FeedbackLink {
        try await client.request(method: "POST", path: "/links", body: body)
    }

    func revokeLink(id: String) async throws -> FeedbackLink {
        try await client.request(method: "POST", path: "/links/\(id)/revoke")
    }

    // MARK: - Listings

    /// Brand-scoped — includes inactive listings (unlike GET /marketplace).
    func listings() async throws -> [Listing] {
        try await client.request(method: "GET", path: "/listings")
    }

    func createListing(_ body: ListingCreate) async throws -> Listing {
        try await client.request(method: "POST", path: "/listings", body: body)
    }

    func updateListing(id: String, _ body: ListingUpdate) async throws -> Listing {
        try await client.request(method: "PATCH", path: "/listings/\(id)", body: body)
    }

    func deleteListing(id: String) async throws {
        try await client.requestVoid(method: "DELETE", path: "/listings/\(id)")
    }

    func listingRedemptions(id: String) async throws -> [Redemption] {
        try await client.request(method: "GET", path: "/listings/\(id)/redemptions")
    }

    func updateRedemption(id: String, status: String) async throws -> Redemption {
        try await client.request(method: "PATCH", path: "/redemptions/\(id)", body: RedemptionStatusUpdate(status: status))
    }
}
