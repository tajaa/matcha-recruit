import Foundation

/// Mirrors LikeTarget/LikeState in client/tellus/src/api/types.ts and
/// server/app/tellus/models/tellus.py:TellusLikeState.
enum LikeTarget: String {
    case boardPost = "board_post"
    case boardReply = "board_reply"
    case report
    case listing
}

struct LikeState: Codable {
    let like_count: Int
    let liked_by_me: Bool
}
