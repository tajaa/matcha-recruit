import SwiftUI
import UniformTypeIdentifiers
import AppKit

private struct PendingAttachment: Identifiable, Hashable {
    let id = UUID()
    let data: Data
    let filename: String
    let mimeType: String
    var size: Int { data.count }
    var isImage: Bool { mimeType.hasPrefix("image/") }
}

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
    @State private var pendingAttachments: [PendingAttachment] = []
    @State private var isUploading = false
    @State private var isDragOver = false
    @State private var replyingTo: ChannelMessage? = nil
    @State private var hoveredMessageId: String? = nil
    @State private var lastTypingSentAt: Date = .distantPast
    @State private var showInviteSheet = false
    @State private var inviteToast: String?

    private let ws = ChannelsWebSocket.shared
    private let senderColumnWidth: CGFloat = 160
    private let maxAttachments = 5
    private let maxAttachmentBytes = 10 * 1024 * 1024
    private let allowedExtensions: Set<String> = [
        "jpg", "jpeg", "png", "webp", "gif",
        "pdf", "txt", "csv", "doc", "docx", "mp4", "mov", "mp3",
    ]

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider()
            if isLoading {
                Spacer()
                Text("loading…")
                    .font(.system(size: 11))
                    .foregroundColor(.white.opacity(0.35))
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
            ws.clearCallbacksIfRoomMatches(channelId)
        }
        .sheet(isPresented: $showInviteSheet) {
            InviteToChannelSheet(
                channelId: channelId,
                channelName: channel?.name ?? "channel"
            ) { addedCount in
                inviteToast = "Invited \(addedCount) member\(addedCount == 1 ? "" : "s")"
                Task { await loadChannel() }
            }
        }
    }

    // MARK: - Header

    private var header: some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack(spacing: 0) {
                Text("# ")
                    .font(.system(size: 13))
                    .foregroundColor(.white.opacity(0.4))
                Text(channel?.name.lowercased() ?? "")
                    .font(.system(size: 13, weight: .medium))
                    .foregroundColor(.white.opacity(0.95))
                Spacer()
                HStack(spacing: 6) {
                    if !onlineUsers.isEmpty {
                        Text("●")
                            .font(.system(size: 8))
                            .foregroundColor(Color.matcha500)
                        Text("\(onlineUsers.count) online")
                            .font(.system(size: 10))
                            .foregroundColor(.white.opacity(0.6))
                    }
                    if let count = channel?.memberCount {
                        Text("·")
                            .font(.system(size: 10))
                            .foregroundColor(.white.opacity(0.25))
                        Text("\(count) members")
                            .font(.system(size: 10))
                            .foregroundColor(.white.opacity(0.4))
                    }
                    Button {
                        showInviteSheet = true
                    } label: {
                        HStack(spacing: 3) {
                            Image(systemName: "person.badge.plus").font(.system(size: 10))
                            Text("Invite").font(.system(size: 10, weight: .medium))
                        }
                        .padding(.horizontal, 7)
                        .padding(.vertical, 3)
                        .background(Color.matcha600.opacity(0.2))
                        .foregroundColor(Color.matcha500)
                        .cornerRadius(4)
                    }
                    .buttonStyle(.plain)
                    .help("Invite users to this channel")
                }
            }
            if let desc = channel?.description, !desc.isEmpty {
                Text(desc)
                    .font(.system(size: 10))
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
                                .font(.system(size: 10))
                                .foregroundColor(.white.opacity(0.35))
                        }
                    }
                }
                .padding(.vertical, 14)
                .padding(.horizontal, 16)
                .frame(maxWidth: .infinity, alignment: .topLeading)
            }
            .onChange(of: messages.count) {
                if let last = messages.last {
                    withAnimation { proxy.scrollTo(last.id, anchor: .bottom) }
                }
            }
        }
        .overlay(
            Group {
                if isDragOver {
                    RoundedRectangle(cornerRadius: 8)
                        .stroke(Color.matcha500, style: StrokeStyle(lineWidth: 2, dash: [6]))
                        .padding(8)
                        .overlay(
                            Text("drop files to attach")
                                .font(.system(size: 12))
                                .foregroundColor(Color.matcha500)
                        )
                        .allowsHitTesting(false)
                }
            }
        )
        .onDrop(of: [UTType.fileURL], isTargeted: $isDragOver) { providers in
            handleFileDrop(providers)
            return true
        }
    }

    private func messageRow(_ msg: ChannelMessage) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            // Reply preview — shows the original message this is replying to
            if let rp = msg.replyPreview {
                HStack(alignment: .top, spacing: 6) {
                    RoundedRectangle(cornerRadius: 1)
                        .fill(Color.matcha500.opacity(0.5))
                        .frame(width: 2)
                    VStack(alignment: .leading, spacing: 3) {
                        Text(rp.senderName)
                            .font(.system(size: 10, weight: .semibold))
                            .foregroundColor(Color.matcha500)
                        if !rp.content.isEmpty {
                            Text(rp.content)
                                .font(.system(size: 10))
                                .foregroundColor(.white.opacity(0.5))
                                .lineLimit(2)
                        }
                        // Show attachment thumbnails in reply preview
                        if !rp.attachments.isEmpty {
                            HStack(spacing: 4) {
                                ForEach(rp.attachments.prefix(3), id: \.self) { att in
                                    if att.contentType.hasPrefix("image/"), let url = URL(string: att.url) {
                                        AsyncImage(url: url) { phase in
                                            switch phase {
                                            case .success(let image):
                                                image.resizable()
                                                    .aspectRatio(contentMode: .fill)
                                                    .frame(width: 48, height: 48)
                                                    .clipped()
                                                    .cornerRadius(4)
                                            default:
                                                RoundedRectangle(cornerRadius: 4)
                                                    .fill(Color.white.opacity(0.05))
                                                    .frame(width: 48, height: 48)
                                            }
                                        }
                                    } else {
                                        HStack(spacing: 4) {
                                            Image(systemName: "paperclip")
                                                .font(.system(size: 9))
                                                .foregroundColor(.white.opacity(0.4))
                                            Text(att.filename)
                                                .font(.system(size: 9))
                                                .foregroundColor(.white.opacity(0.4))
                                                .lineLimit(1)
                                        }
                                        .padding(.horizontal, 6)
                                        .padding(.vertical, 3)
                                        .background(Color.white.opacity(0.05))
                                        .cornerRadius(4)
                                    }
                                }
                            }
                        }
                    }
                }
                .padding(.leading, 46)
                .padding(.bottom, 4)
            }

            HStack(alignment: .top, spacing: 10) {
                senderAvatar(msg)
                    .frame(width: 36, height: 36)

                VStack(alignment: .leading, spacing: 2) {
                    HStack(spacing: 6) {
                        Text(msg.senderName)
                            .font(.system(size: 13, weight: .semibold))
                            .foregroundColor(.primary)
                        Text(formatTimestamp(msg.createdAt))
                            .font(.system(size: 10))
                            .foregroundColor(.secondary)
                    }
                    if !msg.content.isEmpty {
                        Text(msg.content)
                            .font(.system(size: 13))
                            .foregroundColor(.primary.opacity(0.9))
                            .textSelection(.enabled)
                            .fixedSize(horizontal: false, vertical: true)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                    if !msg.attachments.isEmpty {
                        attachmentList(msg.attachments)
                    }

                    // Reaction pills
                    if !msg.reactions.isEmpty {
                        HStack(spacing: 4) {
                            ForEach(msg.reactions, id: \.emoji) { reaction in
                                let isMine = reaction.userIds.contains(appState.currentUser?.id ?? "")
                                Button {
                                    toggleReaction(messageId: msg.id, emoji: reaction.emoji)
                                } label: {
                                    HStack(spacing: 3) {
                                        Text(reaction.emoji).font(.system(size: 12))
                                        if reaction.count > 1 {
                                            Text("\(reaction.count)")
                                                .font(.system(size: 10, weight: .medium))
                                                .foregroundColor(isMine ? Color.matcha500 : .white.opacity(0.6))
                                        }
                                    }
                                    .padding(.horizontal, 6)
                                    .padding(.vertical, 2)
                                    .background(isMine ? Color.matcha500.opacity(0.2) : Color.white.opacity(0.08))
                                    .cornerRadius(10)
                                    .overlay(
                                        RoundedRectangle(cornerRadius: 10)
                                            .stroke(isMine ? Color.matcha500.opacity(0.4) : Color.clear, lineWidth: 1)
                                    )
                                }
                                .buttonStyle(.plain)
                            }
                        }
                        .padding(.top, 2)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .padding(.vertical, 4)
        .padding(.horizontal, 4)
        .background(
            RoundedRectangle(cornerRadius: 6)
                .fill(hoveredMessageId == msg.id ? Color.white.opacity(0.04) : Color.clear)
        )
        .onHover { hovering in hoveredMessageId = hovering ? msg.id : nil }
        .overlay(alignment: .topTrailing) {
            if hoveredMessageId == msg.id {
                HStack(spacing: 2) {
                    Button { replyingTo = msg } label: {
                        Image(systemName: "arrowshape.turn.up.left")
                            .font(.system(size: 10))
                            .foregroundColor(.white.opacity(0.7))
                            .frame(width: 24, height: 22)
                            .background(Color.zinc800)
                            .cornerRadius(4)
                    }
                    .buttonStyle(.plain)
                    .help("Reply")

                    ForEach(["👍", "❤️", "😂"], id: \.self) { emoji in
                        Button { toggleReaction(messageId: msg.id, emoji: emoji) } label: {
                            Text(emoji)
                                .font(.system(size: 11))
                                .frame(width: 24, height: 22)
                                .background(Color.zinc800)
                                .cornerRadius(4)
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(4)
            }
        }
        .contentShape(Rectangle())
        .contextMenu {
            Button {
                NSPasteboard.general.clearContents()
                NSPasteboard.general.setString(msg.content, forType: .string)
            } label: {
                Label("Copy text", systemImage: "doc.on.doc")
            }
            .disabled(msg.content.isEmpty)

            Button { replyingTo = msg } label: {
                Label("Reply", systemImage: "arrowshape.turn.up.left")
            }

            Divider()

            Menu {
                ForEach(["👍", "❤️", "🎉", "😂", "🤔", "👀"], id: \.self) { emoji in
                    Button(emoji) {
                        toggleReaction(messageId: msg.id, emoji: emoji)
                    }
                }
            } label: {
                Label("React", systemImage: "face.smiling")
            }
        }
    }

    private func toggleReaction(messageId: String, emoji: String) {
        Task {
            do {
                _ = try await ChannelsService.shared.toggleReaction(
                    channelId: channelId, messageId: messageId, emoji: emoji
                )
            } catch {
                errorMessage = "Reaction failed: \(error.localizedDescription)"
            }
        }
    }

    @ViewBuilder
    private func senderAvatar(_ msg: ChannelMessage) -> some View {
        if let urlStr = msg.senderAvatarUrl, let url = URL(string: urlStr) {
            AsyncImage(url: url) { phase in
                switch phase {
                case .success(let image):
                    image
                        .resizable()
                        .aspectRatio(contentMode: .fill)
                        .frame(width: 36, height: 36)
                        .clipShape(Circle())
                default:
                    avatarFallback(msg.senderName)
                }
            }
        } else {
            avatarFallback(msg.senderName)
        }
    }

    private func avatarFallback(_ name: String) -> some View {
        let initials = name
            .split(separator: " ")
            .prefix(2)
            .compactMap { $0.first.map(String.init) }
            .joined()
            .uppercased()
        let hue = Double(abs(name.hashValue) % 360) / 360.0
        return Circle()
            .fill(Color(hue: hue, saturation: 0.55, brightness: 0.6))
            .frame(width: 36, height: 36)
            .overlay(
                Text(initials.isEmpty ? "?" : initials)
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundColor(.white)
            )
    }

    @ViewBuilder
    private func attachmentList(_ attachments: [ChannelAttachment]) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            ForEach(attachments, id: \.self) { att in
                attachmentView(att)
            }
        }
    }

    @ViewBuilder
    private func attachmentView(_ att: ChannelAttachment) -> some View {
        if att.contentType.hasPrefix("image/"), let url = URL(string: att.url) {
            AsyncImage(url: url) { phase in
                switch phase {
                case .success(let image):
                    image
                        .resizable()
                        .aspectRatio(contentMode: .fit)
                        .frame(maxWidth: 320, maxHeight: 240)
                        .cornerRadius(6)
                default:
                    RoundedRectangle(cornerRadius: 6)
                        .fill(Color.white.opacity(0.05))
                        .frame(width: 200, height: 120)
                        .overlay(ProgressView().controlSize(.small))
                }
            }
            .onTapGesture {
                if let u = URL(string: att.url) { NSWorkspace.shared.open(u) }
            }
        } else {
            Button {
                if let u = URL(string: att.url) { NSWorkspace.shared.open(u) }
            } label: {
                HStack(spacing: 8) {
                    Image(systemName: iconName(for: att.contentType))
                        .font(.system(size: 14))
                        .foregroundColor(Color.matcha500)
                    VStack(alignment: .leading, spacing: 1) {
                        Text(att.filename)
                            .font(.system(size: 12))
                            .foregroundColor(.white.opacity(0.85))
                            .lineLimit(1)
                            .truncationMode(.middle)
                        Text(formatSize(att.size))
                            .font(.system(size: 10))
                            .foregroundColor(.white.opacity(0.4))
                    }
                }
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                .background(Color.white.opacity(0.05))
                .cornerRadius(6)
            }
            .buttonStyle(.plain)
        }
    }

    private func iconName(for contentType: String) -> String {
        if contentType.hasPrefix("video/") { return "play.rectangle" }
        if contentType.hasPrefix("audio/") { return "waveform" }
        if contentType.contains("pdf") { return "doc.richtext" }
        if contentType.contains("csv") || contentType.contains("sheet") { return "tablecells" }
        if contentType.contains("word") || contentType.contains("document") { return "doc.text" }
        return "paperclip"
    }

    private func formatSize(_ bytes: Int) -> String {
        ByteCountFormatter.string(fromByteCount: Int64(bytes), countStyle: .file)
    }

    // MARK: - Input

    private var inputBar: some View {
        VStack(spacing: 8) {
            // Reply banner
            if let reply = replyingTo {
                HStack(spacing: 8) {
                    RoundedRectangle(cornerRadius: 1)
                        .fill(Color.matcha500)
                        .frame(width: 3, height: 24)
                    VStack(alignment: .leading, spacing: 1) {
                        Text("Replying to \(reply.senderName)")
                            .font(.system(size: 10, weight: .semibold))
                            .foregroundColor(Color.matcha500)
                        Text(reply.content.isEmpty ? (reply.attachments.isEmpty ? "" : "📎 attachment") : String(reply.content.prefix(80)))
                            .font(.system(size: 10))
                            .foregroundColor(.white.opacity(0.5))
                            .lineLimit(1)
                    }
                    Spacer()
                    Button { replyingTo = nil } label: {
                        Image(systemName: "xmark")
                            .font(.system(size: 9, weight: .bold))
                            .foregroundColor(.white.opacity(0.4))
                    }
                    .buttonStyle(.plain)
                }
                .padding(.horizontal, 4)
            }

            if !pendingAttachments.isEmpty {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 6) {
                        ForEach(pendingAttachments) { att in
                            pendingChip(att)
                        }
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }

            HStack(alignment: .center, spacing: 8) {
                Text("\(userHandle)@\(channelSlug) ›")
                    .font(.system(size: 11))
                    .foregroundColor(.white.opacity(0.45))
                    .fixedSize()

                Button(action: openFilePicker) {
                    Image(systemName: "paperclip")
                        .font(.system(size: 12))
                        .foregroundColor(.white.opacity(0.55))
                }
                .buttonStyle(.plain)
                .help("Attach files (max \(maxAttachments), 10 MB each)")
                .disabled(pendingAttachments.count >= maxAttachments || isUploading)

                TextField(
                    "",
                    text: $inputText,
                    prompt: Text("type a message").foregroundColor(.white.opacity(0.2)),
                    axis: .vertical
                )
                .textFieldStyle(.plain)
                .font(.system(size: 13))
                .foregroundColor(.white.opacity(0.9))
                .lineLimit(1...4)
                .onChange(of: inputText) {
                    guard !inputText.isEmpty else { return }
                    let now = Date()
                    if now.timeIntervalSince(lastTypingSentAt) >= 2.5 {
                        lastTypingSentAt = now
                        ws.sendTyping(channelId: channelId)
                    }
                }
                .onSubmit(send)

                let canSend = (!inputText.trimmingCharacters(in: .whitespaces).isEmpty || !pendingAttachments.isEmpty) && !isUploading
                Button(action: send) {
                    if isUploading {
                        ProgressView().controlSize(.small)
                    } else {
                        Text("↵")
                            .font(.system(size: 14, weight: .medium))
                            .foregroundColor(canSend ? Color.matcha500 : .white.opacity(0.2))
                    }
                }
                .buttonStyle(.plain)
                .disabled(!canSend)
                .keyboardShortcut(.return, modifiers: .command)
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .background(.regularMaterial)
    }

    private func pendingChip(_ att: PendingAttachment) -> some View {
        HStack(spacing: 6) {
            if att.isImage, let nsImage = NSImage(data: att.data) {
                Image(nsImage: nsImage)
                    .resizable()
                    .aspectRatio(contentMode: .fill)
                    .frame(width: 28, height: 28)
                    .clipped()
                    .cornerRadius(4)
            } else {
                Image(systemName: iconName(for: att.mimeType))
                    .font(.system(size: 12))
                    .foregroundColor(Color.matcha500)
                    .frame(width: 28, height: 28)
                    .background(Color.white.opacity(0.05))
                    .cornerRadius(4)
            }
            Text(att.filename)
                .font(.system(size: 11))
                .foregroundColor(.white.opacity(0.75))
                .lineLimit(1)
                .truncationMode(.middle)
                .frame(maxWidth: 140)
            Button {
                pendingAttachments.removeAll { $0.id == att.id }
            } label: {
                Image(systemName: "xmark")
                    .font(.system(size: 9, weight: .bold))
                    .foregroundColor(.white.opacity(0.5))
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .background(Color.white.opacity(0.06))
        .cornerRadius(6)
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
        let attachmentsToSend = pendingAttachments
        guard !trimmed.isEmpty || !attachmentsToSend.isEmpty else { return }
        guard !isUploading else { return }

        let replyId = replyingTo?.id

        if attachmentsToSend.isEmpty {
            ws.sendMessage(channelId: channelId, content: trimmed, replyToId: replyId)
            inputText = ""
            replyingTo = nil
            return
        }

        isUploading = true
        let content = trimmed
        Task {
            do {
                let files = attachmentsToSend.map { (data: $0.data, filename: $0.filename, mimeType: $0.mimeType) }
                let uploaded = try await ChannelsService.shared.uploadAttachments(
                    channelId: channelId, files: files
                )
                await MainActor.run {
                    ws.sendMessage(channelId: channelId, content: content, attachments: uploaded, replyToId: replyId)
                    inputText = ""
                    replyingTo = nil
                    pendingAttachments.removeAll()
                    isUploading = false
                }
            } catch {
                await MainActor.run {
                    errorMessage = "Upload failed: \(error.localizedDescription)"
                    isUploading = false
                }
            }
        }
    }

    // MARK: - File picker + drop

    private func openFilePicker() {
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = true
        panel.canChooseDirectories = false
        panel.canChooseFiles = true
        panel.allowedContentTypes = allowedExtensions.compactMap { UTType(filenameExtension: $0) }
        if panel.runModal() == .OK {
            for url in panel.urls {
                ingestFile(at: url)
            }
        }
    }

    private func handleFileDrop(_ providers: [NSItemProvider]) {
        for provider in providers {
            provider.loadItem(forTypeIdentifier: UTType.fileURL.identifier) { item, _ in
                guard let data = item as? Data,
                      let url = URL(dataRepresentation: data, relativeTo: nil) else { return }
                Task { @MainActor in ingestFile(at: url) }
            }
        }
    }

    private func ingestFile(at url: URL) {
        let ext = url.pathExtension.lowercased()
        guard allowedExtensions.contains(ext) else {
            errorMessage = "File type .\(ext) not allowed"
            return
        }
        guard pendingAttachments.count < maxAttachments else {
            errorMessage = "Max \(maxAttachments) attachments per message"
            return
        }
        guard let data = try? Data(contentsOf: url) else {
            errorMessage = "Could not read \(url.lastPathComponent)"
            return
        }
        guard data.count <= maxAttachmentBytes else {
            errorMessage = "\(url.lastPathComponent) is too large (max 10 MB)"
            return
        }
        let mime = UTType(filenameExtension: ext)?.preferredMIMEType ?? "application/octet-stream"
        pendingAttachments.append(
            PendingAttachment(data: data, filename: url.lastPathComponent, mimeType: mime)
        )
    }

    private func loadChannel() async {
        isLoading = true
        errorMessage = nil
        do {
            let detail = try await ChannelsService.shared.getChannel(id: channelId)
            channel = detail
            ws.setCurrentRoomName(detail.name)
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
        ws.onReactionUpdate = { messageId, reactions in
            if let idx = messages.firstIndex(where: { $0.id == messageId }) {
                messages[idx].reactions = reactions
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
