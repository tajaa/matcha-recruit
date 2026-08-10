import Foundation
final class BillingService { static let shared = BillingService(); private init() {}
    func subscription() async throws -> CappeSubscription? { let data = try await APIClient.shared.requestData(method: "GET", path: "/billing/subscription"); return try JSONDecoder().decode(CappeSubscription?.self, from: data) }
}
