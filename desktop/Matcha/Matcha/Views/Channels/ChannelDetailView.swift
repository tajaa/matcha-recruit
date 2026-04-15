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
                ProgressView().tint(.secondary)
                Spacer()
            } else if let errorMessage {
                Spacer()
                Text(errorMessage)
                    .foregroundColor(.secondary)
                    .font(.system(size: 12))
                Spacer()
            } else {
                messagesList
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

    private var header: some View {
        HStack(spacing: 10) {
            Image(systemName: channel?.isPaid == true ? "lock" : "number")
                .foregroundColor(.secondary)
            VStack(alignment: .leading, spacing: 2) {
                Text(channel?.name ?? "Channel")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(.white)
                if let desc = channel?.description, !desc.isEmpty {
                    Text(desc)
                        .font(.system(size: 11))
                        .foregroundColor(.secondary)
                        .lineLimit(1)
                }
            }
            Spacer()
            if !onlineUsers.isEmpty {
                HStack(spacing: 4) {
                    Circle().fill(.green).frame(width: 6, height: 6)
                    Text("\(onlineUsers.count) online")
                        .font(.system(size: 11))
                        .foregroundColor(.secondary)
                }
            }
            if let count = channel?.memberCount {
                Text("\(count) members")
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .background(Color.appBackground)
    }

    private var messagesList: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 10) {
                    ForEach(messages, id: \.id) { msg in
                        messageRow(msg)
                            .id(msg.id)
                    }
                    if !typingUsers.isEmpty {
                        Text(typingUsers.values.joined(separator: ", ") + " typing…")
                            .font(.system(size: 10))
                            .foregroundColor(.secondary)
                            .padding(.horizontal, 16)
                    }
                }
                .padding(.vertical, 12)
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
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundColor(.white)
                Text(formatTimestamp(msg.createdAt))
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
            }
            Text(msg.content)
                .font(.system(size: 13))
                .foregroundColor(.white.opacity(0.9))
                .textSelection(.enabled)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, 16)
    }

    private var inputBar: some View {
        HStack(spacing: 8) {
            TextField("Message", text: $inputText, axis: .vertical)
                .textFieldStyle(.roundedBorder)
                .lineLimit(1...4)
                .onChange(of: inputText) {
                    if !inputText.isEmpty {
                        ws.sendTyping(channelId: channelId)
                    }
                }
                .onSubmit(send)
            Button {
                send()
            } label: {
                Image(systemName: "arrow.up.circle.fill")
                    .font(.system(size: 22))
                    .foregroundColor(inputText.trimmingCharacters(in: .whitespaces).isEmpty ? .secondary : Color.matcha500)
            }
            .buttonStyle(.plain)
            .disabled(inputText.trimmingCharacters(in: .whitespaces).isEmpty)
        }
        .padding(12)
        .background(Color.appBackground)
    }

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
        return display.string(from: date)
    }
}
