import Foundation

@Observable
@MainActor
final class ChannelChatViewModel {
    var channel: ChannelDetail?
    var messages: [ChannelMessage] = []
    var onlineUsers: [ChannelOnlineUser] = []
    var typingUsers: [String: String] = [:]
    var isLoading = true
    var errorMessage: String?

    private(set) var channelId: String?
    private var typingClearTask: Task<Void, Never>?
    private let ws = ChannelsWebSocket.shared
    private let service = ChannelsService.shared

    func start(channelId: String) async {
        // Wipe any stale closure from a prior channel BEFORE the await on
        // loadChannel. Otherwise the previous channel's `onMessage` (whose
        // captured `channelId` guard still passes for that prior channel) can
        // fire during this view's REST fetch and append a stale-channel
        // message into the just-replaced `messages` array.
        ws.clearCallbacks()
        self.channelId = channelId
        await loadChannel(channelId: channelId)
        wireCallbacks(channelId: channelId)
        ws.connect()
        ws.joinRoom(channelId: channelId)
    }

    func stop(channelId: String) {
        ws.clearCallbacksIfRoomMatches(channelId)
    }

    func loadChannel(channelId: String) async {
        isLoading = true
        errorMessage = nil
        do {
            let detail = try await service.getChannel(id: channelId)
            channel = detail
            ws.setCurrentRoomName(detail.name)
            messages = detail.messages
            isLoading = false
        } catch {
            errorMessage = error.localizedDescription
            isLoading = false
        }
    }

    private func wireCallbacks(channelId: String) {
        // Closures capture `self` (a class) by reference — mutations propagate
        // to the live SwiftUI view via @Observable tracking.
        ws.onMessage = { [weak self] msg in
            guard let self, msg.channelId == channelId else { return }
            if !self.messages.contains(where: { $0.id == msg.id }) {
                self.messages.append(msg)
            }
        }
        ws.onMessageDeleted = { [weak self] messageId, deletedBy in
            guard let self else { return }
            if let idx = self.messages.firstIndex(where: { $0.id == messageId }) {
                self.messages[idx].deletedAt = ISO8601DateFormatter().string(from: Date())
                self.messages[idx].deletedBy = deletedBy
            }
        }
        ws.onReactionUpdate = { [weak self] messageId, reactions in
            guard let self else { return }
            if let idx = self.messages.firstIndex(where: { $0.id == messageId }) {
                self.messages[idx].reactions = reactions
            }
        }
        ws.onOnlineUsers = { [weak self] users in
            self?.onlineUsers = users
        }
        ws.onUserJoined = { [weak self] user in
            guard let self else { return }
            if !self.onlineUsers.contains(where: { $0.id == user.id }) {
                self.onlineUsers.append(user)
            }
        }
        ws.onUserLeft = { [weak self] user in
            self?.onlineUsers.removeAll { $0.id == user.id }
        }
        ws.onTyping = { [weak self] userId, name in
            guard let self else { return }
            self.typingUsers[userId] = name.lowercased().replacingOccurrences(of: " ", with: "_")
            self.typingClearTask?.cancel()
            self.typingClearTask = Task { [weak self] in
                try? await Task.sleep(for: .seconds(3))
                self?.typingUsers.removeValue(forKey: userId)
            }
        }
        ws.onError = { [weak self] msg in
            self?.errorMessage = msg
        }
    }
}
