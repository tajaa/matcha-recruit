import Foundation

final class BusinessAccessService {
    static let shared = BusinessAccessService()
    private let client = APIClient.shared
    private init() {}

    func memberships() async throws -> [BusinessMembership] {
        try await client.request(method: "GET", path: "/me/businesses")
    }
}
