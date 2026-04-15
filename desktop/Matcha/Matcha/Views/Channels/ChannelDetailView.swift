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
            ws.clearCallbacks()
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
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(.vertical, 4)
        .contentShape(Rectangle())
        .contextMenu {
            Button {
                NSPasteboard.general.clearContents()
                NSPasteboard.general.setString(msg.content, forType: .string)
            } label: {
                Label("Copy text", systemImage: "doc.on.doc")
            }
            .disabled(msg.content.isEmpty)

            Button {
                inputText = "> \(msg.senderName): \(msg.content.prefix(200))\n"
            } label: {
                Label("Reply", systemImage: "arrowshape.turn.up.left")
            }

            Divider()

            Menu {
                ForEach(["👍", "❤️", "🎉", "😂", "🤔", "👀"], id: \.self) { emoji in
                    Button(emoji) {
                        // Placeholder — backend reaction endpoint not yet wired.
                        // For now, append the emoji as a visible reply so the
                        // interaction still feels responsive.
                        ws.sendMessage(channelId: channelId, content: emoji)
                    }
                }
            } label: {
                Label("React", systemImage: "face.smiling")
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
                    if !inputText.isEmpty {
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

        if attachmentsToSend.isEmpty {
            ws.sendMessage(channelId: channelId, content: trimmed)
            inputText = ""
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
                    ws.sendMessage(channelId: channelId, content: content, attachments: uploaded)
                    inputText = ""
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
