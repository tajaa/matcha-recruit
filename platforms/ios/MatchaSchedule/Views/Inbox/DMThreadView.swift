import SwiftUI

struct DMThreadView: View {
    @Environment(AppState.self) private var appState
    let conversationID: String
    let title: String
    @State private var detail: MWInboxConversationDetail?
    @State private var draft = ""
    @State private var sending = false
    @State private var error: String?
    @FocusState private var composing: Bool

    /// Oldest first, newest at the bottom next to the composer. The server
    /// pages newest-first, so its order is not the reading order.
    private var messages: [MWInboxMessage] { DMOrder.chronological(detail?.messages ?? []) }

    private var isGroup: Bool { detail?.isGroup ?? false }

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(spacing: 4) {
                    ForEach(Array(messages.enumerated()), id: \.element.id) { index, message in
                        let previous = index > 0 ? messages[index - 1] : nil
                        let next = index + 1 < messages.count ? messages[index + 1] : nil
                        if DMOrder.startsNewMoment(message, after: previous) {
                            Text(Instant.label(message.createdAt))
                                .font(.caption)
                                .foregroundStyle(Color.secondary)
                                .padding(.top, index == 0 ? 8 : 18)
                                .padding(.bottom, 6)
                        }
                        MessageBubble(
                            message: message,
                            isMine: message.senderId == appState.currentUserID,
                            // Only other people's names: your own bubbles are already
                            // right-aligned in your color.
                            showsSender: isGroup && message.senderId != appState.currentUserID
                                && previous?.senderId != message.senderId,
                            closesRun: next?.senderId != message.senderId
                                || DMOrder.startsNewMoment(next ?? message, after: message)
                        )
                        .id(message.id)
                    }
                    Color.clear.frame(height: 1).id("bottom")
                }
                .padding(.horizontal, 14)
                .padding(.vertical, 12)
                .animation(.default, value: messages.count)
            }
            .scrollDismissesKeyboard(.interactively)
            .defaultScrollAnchor(.bottom)
            .onChange(of: messages.count) { _, _ in
                withAnimation { proxy.scrollTo("bottom", anchor: .bottom) }
            }
            .onChange(of: composing) { _, focused in
                if focused { withAnimation { proxy.scrollTo("bottom", anchor: .bottom) } }
            }
        }
        .safeAreaInset(edge: .bottom) { composer }
        .navigationTitle(title)
        .navigationBarTitleDisplayMode(.inline)
        .toolbar(.hidden, for: .tabBar)
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
        VStack(spacing: 6) {
            if let error {
                Text(error).font(.caption).foregroundStyle(.red)
            }
            HStack(alignment: .bottom, spacing: 8) {
                TextField("Message", text: $draft, axis: .vertical)
                    .lineLimit(1...5)
                    .focused($composing)
                    .padding(.horizontal, 14).padding(.vertical, 9)
                    .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 20, style: .continuous))
                Button { Task { await send() } } label: {
                    if sending {
                        ProgressView().frame(width: 34, height: 34)
                    } else {
                        Image(systemName: "arrow.up.circle.fill").font(.system(size: 34))
                    }
                }
                .disabled(!canSend)
                .accessibilityLabel("Send message")
                .sensoryFeedback(.impact(weight: .light), trigger: messages.count)
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(.bar)
    }

    private var canSend: Bool {
        !sending && !draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    private func refresh() async {
        do {
            let result = try await InboxService.shared.conversation(conversationID)
            withAnimation { detail = result }
            error = nil
            if (result.unreadCount ?? 0) > 0 {
                try await InboxService.shared.markRead(conversationID)
                appState.unreadMessages = try await InboxService.shared.unreadCount()
            }
        } catch {
            if !error.isCancellation { self.error = error.localizedDescription }
        }
    }

    private func send() async {
        let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        sending = true
        defer { sending = false }
        do {
            let message = try await InboxService.shared.sendMessage(text, in: conversationID)
            withAnimation {
                if detail?.messages == nil {
                    detail?.messages = [message]
                } else if detail?.messages?.contains(where: { $0.id == message.id }) != true {
                    detail?.messages?.append(message)
                }
            }
            draft = ""
            error = nil
        } catch { self.error = error.localizedDescription }
    }
}

private struct MessageBubble: View {
    let message: MWInboxMessage
    let isMine: Bool
    let showsSender: Bool
    /// The last bubble of a run from one sender gets a little room below it.
    let closesRun: Bool

    var body: some View {
        HStack {
            if isMine { Spacer(minLength: 48) }
            VStack(alignment: isMine ? .trailing : .leading, spacing: 4) {
                if showsSender {
                    Text(message.senderName).font(.caption).foregroundStyle(Color.secondary)
                        .padding(.horizontal, 6)
                }
                if !message.content.isEmpty {
                    Text(message.content)
                        .foregroundStyle(isMine ? Color.white : Color.primary)
                        .padding(.horizontal, 14).padding(.vertical, 9)
                        .background(isMine ? Color.accentColor : Color(.secondarySystemFill),
                                    in: RoundedRectangle(cornerRadius: 18, style: .continuous))
                }
                ForEach(message.attachments ?? []) { attachment in
                    if let url = URL(string: attachment.url), url.scheme == "https" {
                        Link(destination: url) {
                            Label(attachment.filename, systemImage: attachment.isImage ? "photo" : "paperclip")
                                .font(.caption)
                                .lineLimit(1)
                        }
                        .buttonStyle(.bordered)
                    }
                }
            }
            .padding(.bottom, closesRun ? 6 : 0)
            if !isMine { Spacer(minLength: 48) }
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(isMine ? "You" : message.senderName): \(message.content)")
    }
}

enum DMOrder {
    /// Ascending by send time; the message id breaks ties so equal timestamps
    /// never swap places between polls. Unparseable times sort by their text.
    static func chronological(_ messages: [MWInboxMessage]) -> [MWInboxMessage] {
        messages.sorted { lhs, rhs in
            let left = Instant.date(lhs.createdAt), right = Instant.date(rhs.createdAt)
            if let left, let right, left != right { return left < right }
            if left == nil || right == nil, lhs.createdAt != rhs.createdAt {
                return lhs.createdAt < rhs.createdAt
            }
            return lhs.id < rhs.id
        }
    }

    /// A time label goes above the first message and after any 30-minute gap.
    static func startsNewMoment(_ message: MWInboxMessage, after previous: MWInboxMessage?) -> Bool {
        guard let previous else { return true }
        guard let now = Instant.date(message.createdAt), let before = Instant.date(previous.createdAt) else {
            return false
        }
        return now.timeIntervalSince(before) > 30 * 60
    }
}
