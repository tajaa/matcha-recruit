import SwiftUI

struct ChannelDetailView: View {
    let channelId: String

    @Environment(AppState.self) private var appState
    @State private var channel: ChannelDetail?
    @State private var messages: [ChannelMessage] = []
    @State private var inputText = ""
    @State private var isLoading = true
    @State private var errorMessage: String?
    @State private var onlineUsers: [ChannelOnlineUser] = []
    @State private var typingUsers: [String: String] = [:]
    @State private var typingClearTask: Task<Void, Never>?

    private let ws = ChannelsWebSocket.shared
    private let senderColumnWidth: CGFloat = 160

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider()
            if isLoading {
                Spacer()
                Text("loading…")
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundColor(.white.opacity(0.35))
                Spacer()
            } else if let errorMessage {
                Spacer()
                Text(errorMessage)
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundColor(.white.opacity(0.4))
                Spacer()
            } else {
                messagesList
                Divider()
                inputBar
            }
        }
        .background(
            LinearGradient(
                colors: [Color.black.opacity(0.15), Color.black.opacity(0.05)],
                startPoint: .top,
                endPoint: .bottom
            )
        )
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
        VStack(alignment: .leading, spacing: 2) {
            HStack(spacing: 0) {
                Text("# ")
                    .font(.system(size: 13, design: .monospaced))
                    .foregroundColor(.white.opacity(0.4))
                Text(channel?.name.lowercased() ?? "")
                    .font(.system(size: 13, weight: .medium, design: .monospaced))
                    .foregroundColor(.white.opacity(0.95))
                Spacer()
                HStack(spacing: 6) {
                    if !onlineUsers.isEmpty {
                        Text("●")
                            .font(.system(size: 8))
                            .foregroundColor(Color.matcha500)
                        Text("\(onlineUsers.count) online")
                            .font(.system(size: 10, design: .monospaced))
                            .foregroundColor(.white.opacity(0.6))
                    }
                    if let count = channel?.memberCount {
                        Text("·")
                            .font(.system(size: 10, design: .monospaced))
                            .foregroundColor(.white.opacity(0.25))
                        Text("\(count) members")
                            .font(.system(size: 10, design: .monospaced))
                            .foregroundColor(.white.opacity(0.4))
                    }
                }
            }
            if let desc = channel?.description, !desc.isEmpty {
                Text(desc)
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundColor(.white.opacity(0.35))
                    .lineLimit(1)
                    .padding(.leading, 15)
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .background(.regularMaterial)
    }

    // MARK: - Messages

    private var messagesList: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 10) {
                    ForEach(messages, id: \.id) { msg in
                        messageRow(msg).id(msg.id)
                    }
                    if !typingUsers.isEmpty {
                        HStack(spacing: 0) {
                            Spacer().frame(width: senderColumnWidth + 16)
                            Text("\(typingUsers.values.sorted().joined(separator: ", ")) typing…")
                                .font(.system(size: 10, design: .monospaced))
                                .foregroundColor(.white.opacity(0.35))
                        }
                    }
                }
                .padding(.vertical, 14)
                .padding(.horizontal, 16)
            }
            .onChange(of: messages.count) {
                if let last = messages.last {
                    withAnimation { proxy.scrollTo(last.id, anchor: .bottom) }
                }
            }
        }
    }

    private func messageRow(_ msg: ChannelMessage) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 0) {
            HStack(spacing: 6) {
                Text(handleFor(msg.senderName))
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundColor(.white.opacity(0.55))
                    .lineLimit(1)
                    .truncationMode(.tail)
                Spacer(minLength: 4)
                Text(formatTimestamp(msg.createdAt))
                    .font(.system(size: 10, design: .monospaced))
                    .foregroundColor(.white.opacity(0.3))
            }
            .frame(width: senderColumnWidth, alignment: .leading)
            .padding(.trailing, 12)

            Text(msg.content)
                .font(.system(size: 13))
                .foregroundColor(.white.opacity(0.85))
                .textSelection(.enabled)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    // MARK: - Input

    private var inputBar: some View {
        HStack(alignment: .center, spacing: 8) {
            Text("\(userHandle)@\(channelSlug) ›")
                .font(.system(size: 11, design: .monospaced))
                .foregroundColor(.white.opacity(0.45))
                .fixedSize()

            TextField(
                "",
                text: $inputText,
                prompt: Text("type a message").foregroundColor(.white.opacity(0.2)),
                axis: .vertical
            )
            .textFieldStyle(.plain)
            .font(.system(size: 13, design: .monospaced))
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
                    .font(.system(size: 14, weight: .medium, design: .monospaced))
                    .foregroundColor(canSend ? Color.matcha500 : .white.opacity(0.2))
            }
            .buttonStyle(.plain)
            .disabled(!canSend)
            .keyboardShortcut(.return, modifiers: .command)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .background(.regularMaterial)
    }

    // MARK: - Derived

    private var userHandle: String {
        let email = appState.currentUser?.email ?? "you"
        return email.split(separator: "@").first.map(String.init) ?? "you"
    }

    private var channelSlug: String {
        channel?.slug ?? channel?.name.lowercased().replacingOccurrences(of: " ", with: "-") ?? "channel"
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
            typingUsers[userId] = handleFor(name)
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

    // MARK: - Formatting

    private func handleFor(_ name: String) -> String {
        name.lowercased().replacingOccurrences(of: " ", with: "_")
    }

    private func formatTimestamp(_ iso: String) -> String {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let date = formatter.date(from: iso) ?? ISO8601DateFormatter().date(from: iso)
        guard let date else { return "" }
        let display = DateFormatter()
        display.dateFormat = "HH:mm"
        return display.string(from: date)
    }
}
