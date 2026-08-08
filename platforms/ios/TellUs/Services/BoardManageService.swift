import Foundation

/// Every call takes `brandId`: nil for a brand account managing its own
/// board, REQUIRED (`?brand_id=`) when a consumer-typed moderator moderates
/// 2+ boards (server 400s "Specify brand_id" otherwise). Reads survive a
/// lapsed brand plan; mutations throw APIError.paymentRequired (402).
final class BoardManageService {
    static let shared = BoardManageService()
    private let client = APIClient.shared
    private init() {}

    private func query(_ brandId: String?) -> String {
        guard let brandId else { return "" }
        return "?brand_id=\(brandId)"
    }

    func moderatedBrands() async throws -> [ModeratedBrand] {
        try await client.request(method: "GET", path: "/me/moderated-brands")
    }

    func summary(brandId: String?) async throws -> BoardManageSummary {
        try await client.request(method: "GET", path: "/board/manage" + query(brandId))
    }

    func requests(brandId: String?) async throws -> [BoardJoinRequest] {
        try await client.request(method: "GET", path: "/board/manage/requests" + query(brandId))
    }

    func approveRequest(id: String, brandId: String?) async throws {
        try await client.requestVoid(method: "POST", path: "/board/manage/requests/\(id)/approve" + query(brandId))
    }

    func declineRequest(id: String, brandId: String?) async throws {
        try await client.requestVoid(method: "POST", path: "/board/manage/requests/\(id)/decline" + query(brandId))
    }

    func members(brandId: String?) async throws -> [BoardMemberEntry] {
        try await client.request(method: "GET", path: "/board/manage/members" + query(brandId))
    }

    func removeMember(id: String, brandId: String?) async throws {
        try await client.requestVoid(method: "POST", path: "/board/manage/members/\(id)/remove" + query(brandId))
    }

    func heldReplies(brandId: String?) async throws -> [BoardManageReplyRow] {
        let base = "/board/manage/replies?status=held"
        let suffix = brandId.map { "&brand_id=\($0)" } ?? ""
        return try await client.request(method: "GET", path: base + suffix)
    }

    /// Atomically awards 15 pts (capped 45/day) to the reply's author on the
    /// server side — no clawback if later removed.
    func approveReply(id: String, brandId: String?) async throws {
        try await client.requestVoid(method: "POST", path: "/board/replies/\(id)/approve" + query(brandId))
    }

    func rejectReply(id: String, brandId: String?) async throws {
        try await client.requestVoid(method: "POST", path: "/board/replies/\(id)/reject" + query(brandId))
    }

    func createPost(brandId: String?, _ body: BoardPostCreate) async throws -> BoardPost {
        try await client.request(method: "POST", path: "/board/posts" + query(brandId), body: body)
    }

    func deletePost(id: String, brandId: String?) async throws {
        try await client.requestVoid(method: "DELETE", path: "/board/posts/\(id)" + query(brandId))
    }

    func updatePost(id: String, brandId: String?, _ body: BoardPostUpdate) async throws -> BoardPost {
        try await client.request(method: "PATCH", path: "/board/posts/\(id)" + query(brandId), body: body)
    }

    func team(brandId: String?) async throws -> [BrandTeamMember] {
        try await client.request(method: "GET", path: "/board/team" + query(brandId))
    }

    func addTeamMember(email: String, brandId: String?) async throws -> BrandTeamMember {
        try await client.request(method: "POST", path: "/board/team" + query(brandId), body: TeamMemberAdd(email: email))
    }

    func removeTeamMember(id: String, brandId: String?) async throws {
        try await client.requestVoid(method: "DELETE", path: "/board/team/\(id)" + query(brandId))
    }
}
