import Foundation

/// Consumer-side board endpoints (join/browse/reply). Brand-side moderation
/// lives in BoardManageService.
final class BoardService {
    static let shared = BoardService()
    private let client = APIClient.shared
    private init() {}

    /// 409 if already pending/member or the board is paused.
    func join(slug: String, note: String?) async throws {
        try await client.requestVoid(method: "POST", path: "/b/\(slug)/board/join", body: BoardJoinBody(note: note))
    }

    func memberships() async throws -> [BoardMembership] {
        try await client.request(method: "GET", path: "/me/board-memberships")
    }

    func cancelMembership(id: String) async throws {
        try await client.requestVoid(method: "POST", path: "/me/board-memberships/\(id)/cancel")
    }

    /// 403 if the caller isn't a member.
    func board(slug: String, limit: Int = 20, offset: Int = 0) async throws -> BoardPage {
        try await client.request(method: "GET", path: "/boards/\(slug)?limit=\(limit)&offset=\(offset)")
    }

    func replies(slug: String, postId: String) async throws -> [BoardReply] {
        try await client.request(method: "GET", path: "/boards/\(slug)/posts/\(postId)/replies")
    }

    /// Lands with status == held, awaiting moderation. Rate-limited
    /// 5/min + 30/hr server-side.
    func reply(slug: String, postId: String, body: String) async throws -> BoardReply {
        try await client.request(method: "POST", path: "/boards/\(slug)/posts/\(postId)/replies", body: ReplyCreate(body: body))
    }

    /// Own reply, only while status == held.
    func deleteOwnReply(slug: String, replyId: String) async throws {
        try await client.requestVoid(method: "DELETE", path: "/boards/\(slug)/replies/\(replyId)")
    }
}
