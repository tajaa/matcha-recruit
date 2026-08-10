import Foundation
final class CreatorService { static let shared = CreatorService(); private init() {}
    func me() async throws -> CreatorProfileMe { try await APIClient.shared.request(method: "GET", path: "/creators/me") }
    func create(_ body: CreatorProfileCreate) async throws -> CreatorProfileMe { try await APIClient.shared.request(method: "POST", path: "/creators/me", body: body) }
    func update(_ body: CreatorProfileUpdate) async throws -> CreatorProfileMe { try await APIClient.shared.request(method: "PATCH", path: "/creators/me", body: body) }
    func submit() async throws -> CreatorProfileMe { try await APIClient.shared.request(method: "POST", path: "/creators/me/submit") }
    func earnings() async throws -> [EarningsRow] { try await APIClient.shared.request(method: "GET", path: "/creators/me/earnings") }
}
