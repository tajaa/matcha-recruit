import SwiftUI

/// A single direct-message thread. DMs aren't on the channels socket, so this
/// loads over REST and polls every 5s while visible; sends append the
/// server-returned message.
struct DMThreadView: View {
    let conversationId: String
    let titleHint: String
    @Environment(AppState.self) private var appState

    @State private var detail: MWInboxConversationDetail?
    @State private var text = ""
    @State private var isSending = false
    @State private var errorMessage: String?

    private let service = InboxService.shared
    private let bottomID = "dm-bottom"
    private var myId: String { appState.currentUser?.id ?? "" }
    private var messages: [MWInboxMessage] { detail?.messages ?? [] }

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(spacing: 8) {
                    ForEach(messages) { msg in
                        DMBubble(message: msg, isMine: msg.senderId == myId)
                    }
                    Color.clear.frame(height: 1).id(bottomID)
                }
                .padding(.vertical, 8)
            }
            .onChange(of: messages.count) {
                withAnimation(.easeOut(duration: 0.2)) { proxy.scrollTo(bottomID, anchor: .bottom) }
            }
        }
        .safeAreaInset(edge: .bottom) { composer }
        .navigationTitle(titleHint)
        .navigationBarTitleDisplayMode(.inline)
        .task { await loadAndPoll() }
    }

    private var composer: some View {
        HStack(alignment: .bottom, spacing: 8) {
            TextField("Message", text: $text, axis: .vertical)
                .lineLimit(1...5)
                .padding(.horizontal, 12).padding(.vertical, 8)
                .background(Capsule().fill(Color(.secondarySystemBackground)))
            Button(action: send) {
                if isSending { ProgressView() }
                else { Image(systemName: "arrow.up.circle.fill").font(.system(size: 30)) }
            }
            .disabled(text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || isSending)
        }
        .padding(.horizontal, 12).padding(.vertical, 8)
        .background(.bar)
    }

    private func loadAndPoll() async {
        await refresh()
        try? await service.markRead(conversationId: conversationId)
        while !Task.isCancelled {
            try? await Task.sleep(for: .seconds(5))
            await refresh()
        }
    }

    private func refresh() async {
        do {
            detail = try await service.getConversation(id: conversationId)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func send() {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, !isSending else { return }
        isSending = true
        Task {
            do {
                let msg = try await service.sendMessage(conversationId: conversationId, content: trimmed)
                await MainActor.run {
                    text = ""
                    if detail?.messages == nil {
                        detail?.messages = [msg]
                    } else if !(detail?.messages?.contains(where: { $0.id == msg.id }) ?? false) {
                        detail?.messages?.append(msg)
                    }
                    isSending = false
                }
            } catch {
                await MainActor.run {
                    isSending = false
                    errorMessage = error.localizedDescription
                }
            }
        }
    }
}

private struct DMBubble: View {
    let message: MWInboxMessage
    let isMine: Bool

    var body: some View {
        HStack {
            if isMine { Spacer(minLength: 40) }
            VStack(alignment: isMine ? .trailing : .leading, spacing: 2) {
                if !isMine {
                    Text(message.senderName).font(.caption2).foregroundStyle(.secondary)
                }
                if !message.content.isEmpty {
                    Text(message.content)
                        .padding(.horizontal, 12).padding(.vertical, 8)
                        .background(
                            isMine ? AnyShapeStyle(.tint) : AnyShapeStyle(Color(.secondarySystemBackground)),
                            in: RoundedRectangle(cornerRadius: 16)
                        )
                        .foregroundStyle(isMine ? .white : .primary)
                }
                if let atts = message.attachments {
                    ForEach(atts) { att in
                        Button { SafeURL.open(att.url) } label: {
                            if att.isImage, let u = URL(string: att.url) {
                                AsyncImage(url: u) { phase in
                                    if let image = phase.image { image.resizable().scaledToFill() }
                                    else { Color(.secondarySystemBackground) }
                                }
                                .frame(maxWidth: 200, maxHeight: 200)
                                .clipShape(RoundedRectangle(cornerRadius: 12))
                            } else {
                                Label(att.filename, systemImage: "doc.fill").font(.caption)
                            }
                        }
                        .buttonStyle(.plain)
                    }
                }
                Text(ChatTime.clock(message.createdAt)).font(.caption2).foregroundStyle(.tertiary)
            }
            if !isMine { Spacer(minLength: 40) }
        }
        .padding(.horizontal, 12)
    }
}
