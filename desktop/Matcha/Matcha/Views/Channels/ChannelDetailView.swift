import SwiftUI

struct ChannelDetailView: View {
    let channelId: String

    @State private var channel: ChannelDetail?
    @State private var messages: [ChannelMessage] = []
    @State private var inputText = ""
    @State private var isLoading = true
    @State private var errorMessage: String?
    @State private var onlineUsers: [ChannelOnlineUser] = []
    @State private var typingUsers: [String: String] = [:]
    @State private var typingClearTask: Task<Void, Never>?

    private let ws = ChannelsWebSocket.shared

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider()
            if isLoading {
                Spacer()
                Text("loading")
                    .font(.system(size: 11))
                    .foregroundColor(.white.opacity(0.4))
                Spacer()
            } else if let errorMessage {
                Spacer()
                Text(errorMessage)
                    .font(.system(size: 11))
                    .foregroundColor(.white.opacity(0.4))
                Spacer()
            } else {
                messagesList
                Divider()
                inputBar
            }
        }
        .background(Color.appBackground)
        .task(id: channelId) {
            await loadChannel()
            wireWebSocket()
            ws.connect()
            ws.joinRoom(channelId: channelId)
        }
        .onDisappear {
            ws.leaveRoom(channelId: channelId)
            ws.clearCallbacks()
        }
    }

    // MARK: - Header

    private var header: some View {
        HStack(alignment: .top, spacing: 8) {
            Text("#")
                .font(.system(size: 14))
                .foregroundColor(.white.opacity(0.4))
            VStack(alignment: .leading, spacing: 2) {
                Text(channel?.name ?? "")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(.white.opacity(0.95))
                if let desc = channel?.description, !desc.isEmpty {
                    Text(desc)
                        .font(.system(size: 11))
                        .foregroundColor(.white.opacity(0.4))
                        .lineLimit(1)
                }
            }
            Spacer()
            HStack(spacing: 8) {
                if !onlineUsers.isEmpty {
                    HStack(spacing: 4) {
                        Text("•")
                            .font(.system(size: 12, weight: .bold))
                            .foregroundColor(Color.matcha500)
                        Text("\(onlineUsers.count) online")
                            .font(.system(size: 11))
                            .foregroundColor(.white.opacity(0.6))
                    }
                }
                if let count = channel?.memberCount {
                    Text("·")
                        .font(.system(size: 11))
                        .foregroundColor(.white.opacity(0.3))
                    Text("\(count) members")
                        .font(.system(size: 11))
                        .foregroundColor(.white.opacity(0.4))
                }
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
    }

    // MARK: - Messages

    private var messagesList: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 12) {
                    ForEach(messages, id: \.id) { msg in
                        messageRow(msg).id(msg.id)
                    }
                    if !typingUsers.isEmpty {
                        Text("\(typingUsers.values.sorted().joined(separator: ", ")) typing…")
                            .font(.system(size: 10))
                            .foregroundColor(.white.opacity(0.35))
                            .padding(.horizontal, 16)
                    }
                }
                .padding(.vertical, 14)
            }
            .onChange(of: messages.count) {
                if let last = messages.last {
                    withAnimation { proxy.scrollTo(last.id, anchor: .bottom) }
                }
            }
        }
    }

    private func messageRow(_ msg: ChannelMessage) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack(spacing: 6) {
                Text(msg.senderName)
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(.white.opacity(0.9))
                Text(formatTimestamp(msg.createdAt))
                    .font(.system(size: 10))
                    .foregroundColor(.white.opacity(0.35))
            }
            Text(msg.content)
                .font(.system(size: 13))
                .foregroundColor(.white.opacity(0.75))
                .textSelection(.enabled)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, 16)
    }

    // MARK: - Input

    private var inputBar: some View {
        HStack(alignment: .center, spacing: 8) {
            Text("›")
                .font(.system(size: 14))
                .foregroundColor(.white.opacity(0.35))
            TextField(
                "",
                text: $inputText,
                prompt: Text("message").foregroundColor(.white.opacity(0.25)),
                axis: .vertical
            )
            .textFieldStyle(.plain)
            .font(.system(size: 13))
            .foregroundColor(.white.opacity(0.9))
            .lineLimit(1...4)
            .onChange(of: inputText) {
                if !inputText.isEmpty {
                    ws.sendTyping(channelId: channelId)
                }
            }
            .onSubmit(send)

            let canSend = !inputText.trimmingCharacters(in: .whitespaces).isEmpty
            Button(action: send) {
                Text("↵")
                    .font(.system(size: 14, weight: .medium))
                    .foregroundColor(canSend ? Color.matcha500 : .white.opacity(0.25))
            }
            .buttonStyle(.plain)
            .disabled(!canSend)
            .keyboardShortcut(.return, modifiers: .command)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
    }

    // MARK: - Actions

    private func send() {
        let trimmed = inputText.trimmingCharacters(in: .whitespaces)
        guard !trimmed.isEmpty else { return }
        ws.sendMessage(channelId: channelId, content: trimmed)
        inputText = ""
    }

    private func loadChannel() async {
        isLoading = true
        errorMessage = nil
        do {
            let detail = try await ChannelsService.shared.getChannel(id: channelId)
            channel = detail
            messages = detail.messages
            isLoading = false
        } catch {
            errorMessage = error.localizedDescription
            isLoading = false
        }
    }

    private func wireWebSocket() {
        ws.onMessage = { msg in
            guard msg.channelId == channelId else { return }
            if !messages.contains(where: { $0.id == msg.id }) {
                messages.append(msg)
            }
        }
        ws.onOnlineUsers = { users in
            onlineUsers = users
        }
        ws.onUserJoined = { user in
            if !onlineUsers.contains(where: { $0.id == user.id }) {
                onlineUsers.append(user)
            }
        }
        ws.onUserLeft = { user in
            onlineUsers.removeAll { $0.id == user.id }
        }
        ws.onTyping = { userId, name in
            typingUsers[userId] = name
            typingClearTask?.cancel()
            typingClearTask = Task { @MainActor in
                try? await Task.sleep(for: .seconds(3))
                typingUsers.removeValue(forKey: userId)
            }
        }
        ws.onError = { msg in
            errorMessage = msg
        }
    }

    private func formatTimestamp(_ iso: String) -> String {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let date = formatter.date(from: iso) ?? ISO8601DateFormatter().date(from: iso)
        guard let date else { return "" }
        let display = DateFormatter()
        display.dateStyle = .none
        display.timeStyle = .short
        return display.string(from: date).lowercased()
    }
}
