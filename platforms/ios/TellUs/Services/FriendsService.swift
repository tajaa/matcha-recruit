import Foundation

final class FriendsService {
    static let shared = FriendsService()
    private let client = APIClient.shared
    private init() {}

    func handleAvailable(_ handle: String) async throws -> TellusHandleAvailability {
        let query = PlacesService.queryString([URLQueryItem(name: "handle", value: handle)])
        return try await client.request(method: "GET", path: "/friends/handle-available" + query)
    }

    func claimHandle(_ handle: String) async throws -> TellusAccount {
        try await client.request(method: "POST", path: "/me/handle", body: TellusHandleClaim(handle: handle))
    }

    func search(_ query: String, limit: Int = 20) async throws -> [FriendSummary] {
        let qs = PlacesService.queryString([
            URLQueryItem(name: "q", value: query), URLQueryItem(name: "limit", value: String(limit)),
        ])
        return try await client.request(method: "GET", path: "/friends/search" + qs)
    }

    func suggestions(limit: Int = 20) async throws -> [FriendSummary] {
        let qs = PlacesService.queryString([URLQueryItem(name: "limit", value: String(limit))])
        return try await client.request(method: "GET", path: "/friends/suggestions" + qs)
    }

    func request(accountId: String? = nil, handle: String? = nil, source: String = "search") async throws -> FriendRequestResult {
        try await client.request(method: "POST", path: "/friends/requests", body: FriendRequestCreate(account_id: accountId, handle: handle, source: source))
    }

    func accept(requestId: String) async throws -> FriendSummary {
        try await client.request(method: "POST", path: "/friends/requests/\(requestId)/accept")
    }

    func decline(requestId: String) async throws {
        try await client.requestVoid(method: "POST", path: "/friends/requests/\(requestId)/decline")
    }

    func cancel(requestId: String) async throws {
        try await client.requestVoid(method: "POST", path: "/friends/requests/\(requestId)/cancel")
    }

    func requests(direction: FriendRequestDirection) async throws -> [FriendRequest] {
        let qs = PlacesService.queryString([URLQueryItem(name: "direction", value: direction.rawValue)])
        return try await client.request(method: "GET", path: "/me/friend-requests" + qs)
    }

    func requestCount() async throws -> FriendRequestCount {
        try await client.request(method: "GET", path: "/me/friend-requests/count")
    }

    func friends(query: String? = nil, limit: Int = 50, offset: Int = 0) async throws -> FriendListPage {
        let qs = PlacesService.queryString([
            URLQueryItem(name: "q", value: query), URLQueryItem(name: "limit", value: String(limit)),
            URLQueryItem(name: "offset", value: String(offset)),
        ])
        return try await client.request(method: "GET", path: "/me/friends" + qs)
    }

    func removeFriend(accountId: String) async throws {
        try await client.requestVoid(method: "DELETE", path: "/me/friends/\(accountId)")
    }

    func profile(accountId: String) async throws -> FriendProfile {
        try await client.request(method: "GET", path: "/people/\(accountId)")
    }

    func profile(handle: String) async throws -> FriendProfile {
        try await client.request(method: "GET", path: "/people/by-handle/\(handle)")
    }

    func feed(cursor: String? = nil, limit: Int = 20) async throws -> FriendActivityPage {
        let qs = PlacesService.queryString([
            URLQueryItem(name: "cursor", value: cursor), URLQueryItem(name: "limit", value: String(limit)),
        ])
        return try await client.request(method: "GET", path: "/me/feed" + qs)
    }

    func invite() async throws -> FriendInvite { try await client.request(method: "GET", path: "/me/friend-invite") }
    func rotateInvite() async throws -> FriendInvite { try await client.request(method: "POST", path: "/me/friend-invite/rotate") }
    func invitePreview(token: String) async throws -> InvitePreview { try await client.request(method: "GET", path: "/friends/invite/\(token)") }
    func redeemInvite(token: String) async throws -> FriendSummary { try await client.request(method: "POST", path: "/friends/invite/\(token)/redeem") }
}
