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
                                .font(TypeScale.caption)
                                .foregroundStyle(Palette.inkFaint)
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
                        .transition(.asymmetric(
                            insertion: .scale(scale: 0.92, anchor: message.senderId == appState.currentUserID ? .bottomTrailing : .bottomLeading)
                                .combined(with: .opacity),
                            removal: .opacity
                        ))
                    }
                    Color.clear.frame(height: 1).id("bottom")
                }
                .padding(.horizontal, 14)
                .padding(.vertical, 12)
                .animation(.spring(response: 0.4, dampingFraction: 0.82), value: messages.count)
            }
            .scrollIndicators(.hidden)
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
        .ambientBackground()
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
                Text(error).font(TypeScale.caption).foregroundStyle(Palette.alert)
            }
            HStack(alignment: .bottom, spacing: 10) {
                TextField("Message", text: $draft, axis: .vertical)
                    .font(TypeScale.body)
                    .lineLimit(1...5)
                    .focused($composing)
                    .padding(.horizontal, 16).padding(.vertical, 11)
                    .glassControl(in: RoundedRectangle(cornerRadius: 22, style: .continuous), interactive: false)
                Button { Task { await send() } } label: {
                    Group {
                        if sending { ProgressView().tint(.white) }
                        else { Image(systemName: "arrow.up").font(.system(size: 17, weight: .bold)) }
                    }
                    .foregroundStyle(.white)
                    .frame(width: 44, height: 44)
                    .background(Circle().fill(Palette.leafGradient))
                    .shadow(color: Palette.leaf.opacity(canSend ? 0.4 : 0), radius: 10, y: 5)
                    .opacity(canSend || sending ? 1 : 0.4)
                    .scaleEffect(canSend ? 1 : 0.9)
                    .animation(.spring(response: 0.3, dampingFraction: 0.7), value: canSend)
                }
                .disabled(!canSend)
                .accessibilityLabel("Send message")
                .sensoryFeedback(.impact(weight: .light), trigger: messages.count)
            }
        }
        .padding(.horizontal, 12)
        .padding(.top, 8)
        .padding(.bottom, 8)
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
    /// The last bubble of a run from one sender gets the tail corner.
    let closesRun: Bool

    private var shape: UnevenRoundedRectangle {
        let tail: CGFloat = closesRun ? 6 : 20
        return UnevenRoundedRectangle(
            topLeadingRadius: 20,
            bottomLeadingRadius: isMine ? 20 : tail,
            bottomTrailingRadius: isMine ? tail : 20,
            topTrailingRadius: 20,
            style: .continuous
        )
    }

    var body: some View {
        HStack {
            if isMine { Spacer(minLength: 48) }
            VStack(alignment: isMine ? .trailing : .leading, spacing: 4) {
                if showsSender {
                    Text(message.senderName).font(TypeScale.caption).foregroundStyle(Palette.inkSoft)
                        .padding(.horizontal, 6)
                }
                if !message.content.isEmpty {
                    Text(message.content)
                        .font(TypeScale.body)
                        .foregroundStyle(isMine ? .white : Palette.ink)
                        .padding(.horizontal, 14).padding(.vertical, 10)
                        .background {
                            if isMine {
                                shape.fill(Palette.leafGradient)
                            } else {
                                shape.fill(.ultraThinMaterial)
                                    .overlay(shape.fill(Color.white.opacity(0.35)))
                                    .overlay(shape.strokeBorder(Color.white.opacity(0.6), lineWidth: 0.8))
                            }
                        }
                        .shadow(color: (isMine ? Palette.leaf : Palette.shadow).opacity(isMine ? 0.25 : 0.06), radius: 8, y: 4)
                }
                ForEach(message.attachments ?? []) { attachment in
                    if let url = URL(string: attachment.url), url.scheme == "https" {
                        Link(destination: url) {
                            Label(attachment.filename, systemImage: attachment.isImage ? "photo" : "paperclip")
                                .font(TypeScale.caption)
                                .lineLimit(1)
                                .padding(.horizontal, 12).padding(.vertical, 8)
                                .glassSurface(cornerRadius: 14, elevated: false)
                        }
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
