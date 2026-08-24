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
    /// Consumer: open a shoutout offer from a universal link.
    case shoutoutOffer(token: String)
    case shoutoutCode(code: String)
    case friendRequests(highlightRequestId: String)
    case friendProfile(accountId: String, name: String)
    case friendInvite(token: String)

    var id: String {
        switch self {
        case .boardFeed(let slug, _): return "board-\(slug)"
        case .dmThread(let id): return "thread-\(id)"
        case .report(let id): return "report-\(id)"
        case .boardManage(let slug): return "board-manage-\(slug ?? "own")"
        case .promoClaim(let token): return "promo-\(token)"
        case .shoutoutOffer(let token): return "shoutout-offer-\(token)"
        case .shoutoutCode(let code): return "shoutout-code-\(code)"
        case .friendRequests(let id): return "friend-requests-\(id)"
        case .friendProfile(let id, _): return "friend-profile-\(id)"
        case .friendInvite(let token): return "friend-invite-\(token)"
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
        case "friend_request":
            guard let id = userInfo["reference_id"] as? String else { return nil }
            return .friendRequests(highlightRequestId: id)
        case "friend_accepted", "friend_added":
            guard let id = userInfo["reference_id"] as? String else { return nil }
            return .friendProfile(accountId: id, name: userInfo["name"] as? String ?? "Friend")
        default:
            return nil
        }
    }

    /// Parse the web URL used by offer links. Supports both the apex URL and
    /// the `/tellus` path handed to the app by Universal Links.
    static func parse(url: URL) -> DeepLinkRoute? {
        guard url.scheme?.lowercased() == "https",
              let host = url.host?.lowercased(),
              host == "hey-matcha.com" || host == "www.hey-matcha.com" else { return nil }
        let components = url.pathComponents.filter { $0 != "/" && !$0.isEmpty }
        let tokenIndex: Int?
        if components.count == 3, components[0] == "tellus", components[1] == "o" {
            tokenIndex = 2
        } else if components.count == 2, components[0] == "o" {
            tokenIndex = 1
        } else {
            tokenIndex = nil
        }
        if let tokenIndex, components[tokenIndex] != "code" {
            return .shoutoutOffer(token: components[tokenIndex])
        }
        if components.count == 4, components[0] == "tellus", components[1] == "o", components[2] == "code" {
            return components[3].isEmpty ? nil : .shoutoutCode(code: components[3])
        }
        if components.count == 3, components[0] == "o", components[1] == "code" {
            return components[2].isEmpty ? nil : .shoutoutCode(code: components[2])
        }
        return nil
    }
}
