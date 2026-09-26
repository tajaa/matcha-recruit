import Foundation

/// Display helpers for direct-message conversations — title + avatar derive from
/// the non-self participants (or the explicit group title).
enum DM {
    static func title(_ conv: MWInboxConversation, myId: String) -> String {
        if let t = conv.title, !t.isEmpty { return t }
        let others = (conv.participants ?? []).filter { $0.userId != myId }
        if others.isEmpty { return "You" }
        return others.map(\.name).joined(separator: ", ")
    }

    static func title(_ detail: MWInboxConversationDetail, myId: String) -> String {
        if let t = detail.title, !t.isEmpty { return t }
        let others = (detail.participants ?? []).filter { $0.userId != myId }
        if others.isEmpty { return "You" }
        return others.map(\.name).joined(separator: ", ")
    }

    static func avatar(_ conv: MWInboxConversation, myId: String) -> (url: String?, name: String) {
        let other = (conv.participants ?? []).first { $0.userId != myId }
        return (other?.avatarUrl, other?.name ?? title(conv, myId: myId))
    }
}
