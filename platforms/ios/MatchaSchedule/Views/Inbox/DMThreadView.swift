import SwiftUI

struct DMThreadView: View {
    @Environment(AppState.self) private var appState
    let conversationID: String
    let title: String
    @State private var detail: MWInboxConversationDetail?
    @State private var draft = ""
    @State private var sending = false
    @State private var error: String?

    private var messages: [MWInboxMessage] { detail?.messages ?? [] }

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(spacing: 9) {
                    ForEach(messages) { message in
                        MessageBubble(message: message, isMine: message.senderId == appState.currentUserID)
                    }
                    Color.clear.frame(height: 1).id("bottom")
                }
                .padding(.vertical, 12)
            }
            .onChange(of: messages.count) { _, _ in
                withAnimation { proxy.scrollTo("bottom", anchor: .bottom) }
            }
        }
        .safeAreaInset(edge: .bottom) { composer }
        .navigationTitle(title)
        .navigationBarTitleDisplayMode(.inline)
        .task {
            await refresh()
            while !Task.isCancelled {
                do { try await Task.sleep(for: .seconds(5)) }
                catch { break }
                await refresh()
            }
        }
    }

    private var composer: some View {
        VStack(spacing: 3) {
            if let error { Text(error).font(.footnote).foregroundStyle(.red) }
            HStack(alignment: .bottom, spacing: 8) {
                TextField("Message", text: $draft, axis: .vertical)
                    .lineLimit(1...5).textFieldStyle(.roundedBorder)
                Button { Task { await send() } } label: {
                    if sending { ProgressView() }
                    else { Image(systemName: "arrow.up.circle.fill").font(.system(size: 28)) }
                }
                .disabled(sending || draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                .accessibilityLabel("Send message")
            }
            .padding(.horizontal, 12).padding(.vertical, 8)
        }
        .background(.bar)
    }

    private func refresh() async {
        do {
            let result = try await InboxService.shared.conversation(conversationID)
            detail = result
            error = nil
            if (result.unreadCount ?? 0) > 0 {
                try await InboxService.shared.markRead(conversationID)
                appState.unreadMessages = try await InboxService.shared.unreadCount()
            }
        } catch { self.error = error.localizedDescription }
    }

    private func send() async {
        let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        sending = true
        defer { sending = false }
        do {
            let message = try await InboxService.shared.sendMessage(text, in: conversationID)
            if detail?.messages == nil {
                detail?.messages = [message]
            } else if detail?.messages?.contains(where: { $0.id == message.id }) != true {
                detail?.messages?.append(message)
            }
            draft = ""
            error = nil
        } catch { self.error = error.localizedDescription }
    }
}

private struct MessageBubble: View {
    let message: MWInboxMessage
    let isMine: Bool

    var body: some View {
        HStack {
            if isMine { Spacer(minLength: 40) }
            VStack(alignment: isMine ? .trailing : .leading, spacing: 4) {
                if !isMine { Text(message.senderName).font(.caption2).foregroundStyle(.secondary) }
                if !message.content.isEmpty {
                    Text(message.content)
                        .padding(.horizontal, 12).padding(.vertical, 8)
                        .foregroundStyle(isMine ? .white : .primary)
                        .background(isMine ? Color.brown : Color(.secondarySystemBackground),
                                    in: RoundedRectangle(cornerRadius: 16))
                }
                ForEach(message.attachments ?? []) { attachment in
                    if let url = URL(string: attachment.url), url.scheme == "https" {
                        Link(attachment.filename, destination: url)
                            .font(.caption).lineLimit(1)
                    }
                }
                Text(message.createdAt.prefix(16).replacingOccurrences(of: "T", with: " "))
                    .font(.caption2).foregroundStyle(.tertiary)
            }
            if !isMine { Spacer(minLength: 40) }
        }
        .padding(.horizontal, 12)
    }
}
