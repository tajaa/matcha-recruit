import Foundation

/// Pure counter — likes on board posts, board replies, published reviews,
/// and reward listings. No points, no notifications. Not the brand heart
/// (ReportDetailViewModel.toggleHeart) — a separate consumer-facing action.
final class LikesService {
    static let shared = LikesService()
    private let client = APIClient.shared
    private init() {}

    /// Idempotent — a second tap returns the same count, never a conflict.
    func like(_ target: LikeTarget, id: String) async throws -> LikeState {
        try await client.request(method: "POST", path: "/likes/\(target.rawValue)/\(id)")
    }

    /// Self-scoped server-side — always succeeds even if the caller never liked it.
    func unlike(_ target: LikeTarget, id: String) async throws -> LikeState {
        try await client.request(method: "DELETE", path: "/likes/\(target.rawValue)/\(id)")
    }
}
