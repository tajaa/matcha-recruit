import Foundation
import Observation

/// Holds the channel list + unread state for `ChannelListView`. The detail/chat
/// VM is the shared `ChannelChatViewModel` (vended by `WorkDetailVMStore`); this
/// is iOS-only list state.
@MainActor
@Observable
final class ChannelListViewModel {
    var channels: [ChannelSummary] = []
    var isLoading = false
    var errorMessage: String?

    private let service = ChannelsService.shared

    func load(initial: Bool = false) async {
        if initial { isLoading = true }
        errorMessage = nil
        do {
            let list = try await service.listChannels()
            channels = sorted(list)
            // Subscribe to every channel on the socket so background messages
            // (and unread bumps) arrive even when their chat isn't open.
            ChannelsWebSocket.shared.joinBackgroundRooms(list.map { (id: $0.id, name: $0.name) })
        } catch {
            errorMessage = error.localizedDescription
        }
        isLoading = false
    }

    /// A live message arrived for a channel the user isn't currently viewing.
    func bumpUnread(channelId: String, preview: String, at iso: String) {
        guard let i = channels.firstIndex(where: { $0.id == channelId }) else { return }
        channels[i].unreadCount += 1
        channels = sorted(channels)
    }

    func clearUnread(channelId: String) {
        guard let i = channels.firstIndex(where: { $0.id == channelId }),
              channels[i].unreadCount != 0 else { return }
        channels[i].unreadCount = 0
    }

    private func sorted(_ list: [ChannelSummary]) -> [ChannelSummary] {
        list.sorted {
            (ChatTime.date($0.lastMessageAt) ?? .distantPast) >
            (ChatTime.date($1.lastMessageAt) ?? .distantPast)
        }
    }
}
