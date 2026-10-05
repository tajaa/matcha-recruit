import Foundation

/// Display helpers for direct-message conversations — the title derives from
/// the non-self participants (or the explicit group title).
enum DM {
    static func title(_ conv: MWInboxConversation, myId: String) -> String {
        if let t = conv.title, !t.isEmpty { return t }
        let others = (conv.participants ?? []).filter { $0.userId != myId }
        if others.isEmpty { return "You" }
        return others.map(\.name).joined(separator: ", ")
    }
}
