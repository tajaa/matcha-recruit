import SwiftUI
import AppKit
import UniformTypeIdentifiers

extension ChannelDetailView {
    /// Turn a chat message into a kanban ticket: AI-draft it against the linked
    /// project, then open the review sheet. Project chats only (guarded by the
    /// caller passing onCreateTicket).
    func startTicketDraft(from msg: ChannelMessage) {
        guard let pid = vm.channel?.projectId, !draftingTicket else { return }
        let text = msg.content.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        draftingTicket = true
        ticketDraftError = nil
        Task {
            do {
                // One-shot on purpose: turning a chat message into a ticket is
                // an incidental right-click, not a repo investigation. The
                // durable agent path takes minutes and holds the board's
                // one-live-run lock.
                let draft = try await MatchaWorkService.shared.draftTaskFromPrompt(
                    projectId: pid, prompt: text, model: ticketDraftModel, useAgent: false
                )
                await MainActor.run {
                    draftingTicket = false
                    ticketDraft = draft
                    showTicketReview = true
                }
            } catch {
                await MainActor.run {
                    draftingTicket = false
                    if case APIError.httpError(let code, _) = error, code == 429 {
                        ticketDraftError = "AI drafting limit reached — try again later."
                    } else if case APIError.httpError(let code, _) = error, code == 402 {
                        ticketDraftError = "This workspace has reached its AI token budget."
                    } else {
                        ticketDraftError = "Couldn't draft a ticket from that message."
                    }
                }
            }
        }
    }

    /// Adapt a channel attachment to the shared in-app preview model. Lives at
    /// this level (not per-row) so the single hoisted sheet owns presentation.
    func previewModel(_ att: ChannelAttachment, link: String? = nil) -> MWProjectFile {
        MWProjectFile(
            id: att.url, projectId: nil, taskId: nil, uploadedBy: nil,
            filename: att.filename, storageUrl: link ?? att.url,
            contentType: att.contentType, fileSize: att.size, createdAt: nil
        )
    }

    /// Preview an attachment. A private Espresso file is opened through a
    /// short-lived link, fetched first.
    func openAttachment(_ att: ChannelAttachment) {
        guard let inputId = att.privateInputId else {
            previewFile = previewModel(att)
            return
        }
        Task {
            do {
                let link = try await MatchaWorkService.shared.assistantInputLink(inputId)
                await MainActor.run { previewFile = previewModel(att, link: link.absoluteString) }
            } catch {
                await MainActor.run { attachmentNotice = "\(att.filename) isn't available any more." }
            }
        }
    }

    func attachmentNoticeBar(_ notice: String) -> some View {
        HStack(spacing: 6) {
            Image(systemName: "exclamationmark.triangle.fill")
                .font(.system(size: 11))
                .foregroundColor(.orange)
            Text(notice)
                .font(.system(size: 11))
                .foregroundColor(appState.themeText.opacity(0.8))
                .lineLimit(2)
            Spacer(minLength: 0)
            Button { attachmentNotice = nil } label: {
                Image(systemName: "xmark").font(.system(size: 9))
            }
            .buttonStyle(.plain)
            .foregroundColor(appState.themeText.opacity(0.5))
        }
        .padding(.horizontal, 12).padding(.vertical, 6)
        .background(Color.orange.opacity(0.08))
        .task(id: notice) {
            try? await Task.sleep(for: .seconds(6))
            if attachmentNotice == notice { attachmentNotice = nil }
        }
    }

    func deleteMessage(_ msg: ChannelMessage) {
        Task {
            do {
                try await ChannelsService.shared.deleteMessage(channelId: channelId, messageId: msg.id)
                await MainActor.run {
                    if let idx = vm.messages.firstIndex(where: { $0.id == msg.id }) {
                        vm.messages[idx].deletedAt = ISO8601DateFormatter().string(from: Date())
                        vm.messages[idx].deletedBy = appState.currentUser?.id ?? ""
                    }
                }
            } catch {
                vm.errorMessage = "Delete failed: \(error.localizedDescription)"
            }
        }
    }

    func toggleReaction(messageId: String, emoji: String) {
        Task {
            do {
                _ = try await ChannelsService.shared.toggleReaction(
                    channelId: channelId, messageId: messageId, emoji: emoji
                )
            } catch {
                vm.errorMessage = "Reaction failed: \(error.localizedDescription)"
            }
        }
    }

    // MARK: - Derived

    var userHandle: String {
        let email = appState.currentUser?.email ?? "you"
        return email.split(separator: "@").first.map(String.init) ?? "you"
    }

    /// Left of the composer. In the assistant chat the channel's slug is an
    /// opaque `espresso-<ids>` string, so it reads "you@espresso".
    var composerPrompt: String {
        isAssistant ? "\(userHandle)@espresso" : "\(userHandle)@\(channelSlug)"
    }

    var assistantModels: AssistantModelMenu { AssistantModelMenu(workspace: appState.entitlements?.workspace) }

    var channelSlug: String {
        vm.channel?.slug ?? vm.channel?.name.lowercased().replacingOccurrences(of: " ", with: "-") ?? "channel"
    }

    // MARK: - Actions

    /// Push a value into the composer's local draft (prefill on edit, clear
    /// after send) by bumping the seed nonce the composer watches.
    func seedComposer(_ s: String) {
        composerSeed = s
        composerSeedNonce += 1
    }

    /// One-tap threaded reply (agent-card question buttons). It takes the
    /// same send path as typing the reply, so the server treats it
    /// identically, but it is never queued: offline it sends nothing and
    /// returns false, and the card keeps its buttons, since a stale answer
    /// replayed later is worse than none.
    @discardableResult
    func quickReply(to message: ChannelMessage, text: String) -> Bool {
        postMessage(text, replyTo: message, queue: false)
    }

    /// The one chat send: sends over the socket (or queues it, unless `queue`
    /// is false), then shows the optimistic row the echo will replace.
    /// Returns false, showing nothing, when an unqueued send can't go out.
    @discardableResult
    func postMessage(
        _ content: String, attachments: [ChannelAttachment] = [],
        replyTo target: ChannelMessage?, queue: Bool = true
    ) -> Bool {
        let cmid = UUID().uuidString
        guard ws.sendMessage(
            channelId: channelId, content: content, attachments: attachments,
            replyToId: target?.id, clientMessageId: cmid, queue: queue,
            assistantModel: isAssistant ? assistantModels.value(for: assistantModelPick) : nil
        ) else { return false }
        appendOptimisticMessage(
            clientMessageId: cmid,
            content: content,
            attachments: attachments,
            replyToId: target?.id,
            replyPreview: target.map { ReplyPreview(
                id: $0.id,
                senderName: $0.senderName,
                content: $0.content,
                attachments: $0.attachments,
            ) },
        )
        selfSendScroll += 1
        return true
    }

    func send(_ draft: String) {
        let trimmed = draft.trimmingCharacters(in: .whitespaces)
        // Edit mode: commit the edit instead of sending a new message.
        if let editing = editingMessage {
            editingMessage = nil
            seedComposer("")
            guard !trimmed.isEmpty else { return }
            Task { await vm.editMessage(editing, newContent: trimmed) }
            return
        }
        // Weave in a referenced kanban ticket (from "Chat about this ticket")
        // as a reply-style prefix so the channel message carries the ticket
        // context. Captured + cleared on send.
        var content = trimmed
        if let ref = appState.pendingTicketRef {
            let colLabel = ref.column.replacingOccurrences(of: "_", with: " ").capitalized
            // Machine-readable marker the message row renders as a clickable
            // ticket chip. Sanitize the title of the delimiter chars so it
            // round-trips; clients that don't parse it just see the raw text.
            let safeTitle = ref.title
                .replacingOccurrences(of: "⟦", with: "")
                .replacingOccurrences(of: "⟧", with: "")
                .replacingOccurrences(of: "|", with: "/")
            let token = "⟦ticket:\(ref.id)|\(safeTitle)|\(colLabel)⟧"
            content = trimmed.isEmpty ? token : "\(token)\n\(trimmed)"
            appState.pendingTicketRef = nil
        }
        let attachmentsToSend = pendingAttachments
        guard !content.isEmpty || !attachmentsToSend.isEmpty else { return }
        guard !isUploading else { return }

        let target = replyingTo

        if attachmentsToSend.isEmpty {
            postMessage(content, replyTo: target)
            seedComposer("")
            replyingTo = nil
            return
        }

        isUploading = true
        Task {
            do {
                let files = attachmentsToSend.map { (data: $0.data, filename: $0.filename, mimeType: $0.mimeType) }
                let uploaded = try await ChannelsService.shared.uploadAttachments(
                    channelId: channelId, files: files
                )
                await MainActor.run {
                    postMessage(content, attachments: uploaded, replyTo: target)
                    seedComposer("")
                    replyingTo = nil
                    pendingAttachments.removeAll()
                    isUploading = false
                }
            } catch {
                await MainActor.run {
                    // The draft and its files stay, so a retry is one click.
                    attachmentNotice = Self.uploadFailure(error)
                    isUploading = false
                }
            }
        }
    }

    func appendOptimisticMessage(
        clientMessageId: String,
        content: String,
        attachments: [ChannelAttachment],
        replyToId: String?,
        replyPreview: ReplyPreview?,
    ) {
        guard let me = appState.currentUser else { return }
        let pending = ChannelMessage(
            id: clientMessageId,
            channelId: channelId,
            senderId: me.id,
            senderName: me.name ?? me.email,
            senderAvatarUrl: me.avatarUrl,
            content: content,
            attachments: attachments,
            replyToId: replyToId,
            replyPreview: replyPreview,
            reactions: [],
            createdAt: ISO8601DateFormatter().string(from: Date()),
            editedAt: nil,
            mentionedUserIds: nil,
            clientMessageId: clientMessageId,
            pending: true,
        )
        vm.messages.append(pending)
        vm.schedulePendingTimeout(clientMessageId: clientMessageId)
    }

    // MARK: - File picker + drop

    func openFilePicker() {
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = true
        panel.canChooseDirectories = false
        panel.canChooseFiles = true
        panel.allowsOtherFileTypes = true   // allow any type; validated on ingest
        if panel.runModal() == .OK {
            for url in panel.urls {
                ingestFile(at: url)
            }
        }
    }

    func handleFileDrop(_ providers: [NSItemProvider]) {
        for provider in providers {
            provider.loadItem(forTypeIdentifier: UTType.fileURL.identifier) { item, _ in
                guard let data = item as? Data,
                      let url = URL(dataRepresentation: data, relativeTo: nil) else { return }
                Task { @MainActor in ingestFile(at: url) }
            }
        }
    }

    func ingestFile(at url: URL) {
        let size = (try? url.resourceValues(forKeys: [.fileSizeKey]).fileSize) ?? 0
        if let refusal = attachmentRules.refusal(filename: url.lastPathComponent, size: size, pending: pendingAttachments) {
            attachmentNotice = refusal
            return
        }
        guard let data = try? Data(contentsOf: url) else {
            attachmentNotice = "Could not read \(url.lastPathComponent)"
            return
        }
        var file = PendingChannelAttachment(
            data: data, filename: url.lastPathComponent,
            mimeType: UTType(filenameExtension: url.pathExtension.lowercased())?.preferredMIMEType
                ?? "application/octet-stream"
        )
        if isAssistant {
            // Espresso reads JPEG, not HEIC: convert an iPhone photo here.
            guard let converted = Self.convertingHEIC(file) else {
                attachmentNotice = "Couldn't convert \(url.lastPathComponent) to JPEG"
                return
            }
            file = converted
        }
        if let refusal = attachmentRules.refusal(filename: file.filename, size: file.size, pending: pendingAttachments) {
            attachmentNotice = refusal
            return
        }
        pendingAttachments.append(file)
    }

    /// A HEIC or HEIF photo as a JPEG; anything else unchanged; nil when the
    /// photo can't be decoded.
    nonisolated static func convertingHEIC(_ file: PendingChannelAttachment) -> PendingChannelAttachment? {
        let ext = (file.filename as NSString).pathExtension.lowercased()
        guard ext == "heic" || ext == "heif" else { return file }
        guard let rep = NSBitmapImageRep(data: file.data),
              let jpeg = rep.representation(using: .jpeg, properties: [.compressionFactor: 0.85])
        else { return nil }
        let stem = (file.filename as NSString).deletingPathExtension
        return PendingChannelAttachment(data: jpeg, filename: "\(stem).jpg", mimeType: "image/jpeg")
    }

    /// The server's own reason when it gave one ("Espresso takes up to 5
    /// files at a time"), else a plain failure.
    nonisolated static func uploadFailure(_ error: Error) -> String {
        if case APIError.httpError(_, let message) = error, !message.isEmpty, !message.hasPrefix("{") {
            return message
        }
        return "Upload failed: \(error.localizedDescription)"
    }

    /// Pull an image off the system clipboard and stage it as an attachment.
    /// Lets the user screenshot to clipboard (⌃⌘⇧4) and paste straight into the
    /// composer — no desktop-file roundtrip. Sandbox-safe (no permission).
    func pasteImageFromClipboard() {
        let pb = NSPasteboard.general
        // Prefer PNG; fall back to TIFF (the format screenshots land in) and
        // transcode to PNG so the upload is consistently image/png.
        let data: Data
        if let png = pb.data(forType: .png) {
            data = png
        } else if let tiff = pb.data(forType: .tiff),
                  let rep = NSBitmapImageRep(data: tiff),
                  let png = rep.representation(using: .png, properties: [:]) {
            data = png
        } else {
            attachmentNotice = "No image on the clipboard — screenshot with ⌃⌘⇧4 first"
            return
        }
        let stamp = Int(Date().timeIntervalSince1970)
        if let refusal = attachmentRules.refusal(filename: "pasted-\(stamp).png", size: data.count, pending: pendingAttachments) {
            attachmentNotice = refusal
            return
        }
        pendingAttachments.append(
            PendingChannelAttachment(data: data, filename: "pasted-\(stamp).png", mimeType: "image/png")
        )
    }
}
