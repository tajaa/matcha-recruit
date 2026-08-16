import Foundation

/// A destination a tapped push notification can route to. Parsed from the APNs
/// payload the Tell-Us backend sends (`server/app/tellus/services/push.py`),
/// whose `type` is the notification kind and whose `reference_id` / `slug` /
/// `name` identify the target.
enum DeepLinkRoute: Hashable, Identifiable {
    /// Consumer: open a brand's regulars board (fan-board post / campaign).
    case boardFeed(slug: String, name: String)
    /// Either side: open a Comms / DM conversation.
    case dmThread(threadId: String)
    /// Brand: open the feedback detail for a new review.
    case report(reportId: String)
    /// Brand: open the board-management screen (a reply is awaiting approval).
    case boardManage(slug: String?)
    /// Consumer: open a promo claim sheet from a campaign push.
    case promoClaim(token: String)

    var id: String {
        switch self {
        case .boardFeed(let slug, _): return "board-\(slug)"
        case .dmThread(let id): return "thread-\(id)"
        case .report(let id): return "report-\(id)"
        case .boardManage(let slug): return "board-manage-\(slug ?? "own")"
        case .promoClaim(let token): return "promo-\(token)"
        }
    }

    /// Parse an APNs `userInfo` payload into a route, or nil when the push is
    /// not a deep-linkable notification kind.
    static func parse(userInfo: [AnyHashable: Any]) -> DeepLinkRoute? {
        guard let type = userInfo["type"] as? String else { return nil }
        switch type {
        case "promo_campaign":
            if let token = userInfo["claim_token"] as? String, !token.isEmpty {
                return .promoClaim(token: token)
            }
            fallthrough
        case "board_post":
            guard let slug = userInfo["slug"] as? String, !slug.isEmpty else { return nil }
            let name = userInfo["name"] as? String ?? slug
            return .boardFeed(slug: slug, name: name)
        case "dm_message", "dm_assignment":
            guard let id = userInfo["reference_id"] as? String else { return nil }
            return .dmThread(threadId: id)
        case "feedback":
            guard let id = userInfo["reference_id"] as? String else { return nil }
            return .report(reportId: id)
        case "board_reply_pending":
            return .boardManage(slug: userInfo["slug"] as? String)
        default:
            return nil
        }
    }
}
