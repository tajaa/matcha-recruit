import Foundation

extension Array where Element == ChannelSummary {
    /// Starred first, then most-recently-active.
    ///
    /// This is the one ordering every channel surface uses — the sidebar list,
    /// the hub rail, and the hub cards each had their own hand-written copy of
    /// it (two spelled as a tuple compare, one as an `if`), so a change to the
    /// rule had three places to miss.
    ///
    /// `lastMessageAt` is an ISO8601 string, so the lexical compare is
    /// chronological; a channel that has never been posted in sorts last.
    ///
    /// Deliberately NOT `@MainActor`: the call sites (a `View`'s async `load()`
    /// and its synchronous computed properties) reach `ChannelStarStore.shared`
    /// exactly this way today, and annotating it would make every one of them
    /// need an `await` they can't give.
    func sortedStarredFirst() -> [ChannelSummary] {
        let stars = ChannelStarStore.shared
        return sorted { a, b in
            let sa = stars.isStarred(a.id)
            let sb = stars.isStarred(b.id)
            if sa != sb { return sa }
            return (a.lastMessageAt ?? "") > (b.lastMessageAt ?? "")
        }
    }
}
