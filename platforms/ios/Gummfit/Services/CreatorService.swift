import Foundation
final class CreatorService { static let shared = CreatorService(); private init() {}
    func me() async throws -> CreatorProfileMe { try await APIClient.shared.request(method: "GET", path: "/creators/me") }
    func create(_ body: CreatorProfileCreate) async throws -> CreatorProfileMe { try await APIClient.shared.request(method: "POST", path: "/creators/me", body: body) }
    func update(_ body: CreatorProfileUpdate) async throws -> CreatorProfileMe { try await APIClient.shared.request(method: "PATCH", path: "/creators/me", body: body) }
    func submit() async throws -> CreatorProfileMe { try await APIClient.shared.request(method: "POST", path: "/creators/me/submit") }
    func replaceSocials(_ body: [CreatorSocialInput]) async throws -> [CreatorSocial] { try await APIClient.shared.request(method: "PUT", path: "/creators/me/socials", body: body) }
    func replacePortfolio(_ body: [CreatorPortfolioInput]) async throws -> [CreatorPortfolioItem] { try await APIClient.shared.request(method: "PUT", path: "/creators/me/portfolio", body: body) }
    func replaceRates(_ body: [CreatorRateInput]) async throws -> [CreatorRate] { try await APIClient.shared.request(method: "PUT", path: "/creators/me/rates", body: body) }
    func earnings() async throws -> [EarningsRow] { try await APIClient.shared.request(method: "GET", path: "/creators/me/earnings") }
}
