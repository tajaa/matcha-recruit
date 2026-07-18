import SwiftUI
import AppKit
import UniformTypeIdentifiers

extension ChannelDetailView {    /// Turn a chat message into a kanban ticket: AI-draft it against the linked
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
                let draft = try await MatchaWorkService.shared.draftTaskFromPrompt(
                    projectId: pid, prompt: text, model: ticketDraftModel
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
                        ticketDraftError = "Daily AI limit reached — try again later."
                    } else {
                        ticketDraftError = "Couldn't draft a ticket from that message."
                    }
                }
            }
        }
    }

    /// Adapt a channel attachment to the shared in-app preview model. Lives at
    /// this level (not per-row) so the single hoisted sheet owns presentation.
    func previewModel(_ att: ChannelAttachment) -> MWProjectFile {
        MWProjectFile(
            id: att.url, projectId: nil, taskId: nil, uploadedBy: nil,
            filename: att.filename, storageUrl: att.url,
            contentType: att.contentType, fileSize: att.size, createdAt: nil
        )
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

        let replyId = replyingTo?.id
        let replyPreviewForOptimistic = replyingTo.map { ReplyPreview(
            id: $0.id,
            senderName: $0.senderName,
            content: $0.content,
            attachments: $0.attachments,
        ) }

        if attachmentsToSend.isEmpty {
            let cmid = UUID().uuidString
            appendOptimisticMessage(
                clientMessageId: cmid,
                content: content,
                attachments: [],
                replyToId: replyId,
                replyPreview: replyPreviewForOptimistic,
            )
            ws.sendMessage(channelId: channelId, content: content, replyToId: replyId, clientMessageId: cmid)
            seedComposer("")
            replyingTo = nil
            selfSendScroll += 1
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
                    let cmid = UUID().uuidString
                    appendOptimisticMessage(
                        clientMessageId: cmid,
                        content: content,
                        attachments: uploaded,
                        replyToId: replyId,
                        replyPreview: replyPreviewForOptimistic,
                    )
                    ws.sendMessage(channelId: channelId, content: content, attachments: uploaded, replyToId: replyId, clientMessageId: cmid)
                    seedComposer("")
                    replyingTo = nil
                    pendingAttachments.removeAll()
                    isUploading = false
                    selfSendScroll += 1
                }
            } catch {
                await MainActor.run {
                    vm.errorMessage = "Upload failed: \(error.localizedDescription)"
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
        let ext = url.pathExtension.lowercased()
        guard !blockedExtensions.contains(ext) else {
            vm.errorMessage = "File type .\(ext) isn't allowed"
            return
        }
        guard pendingAttachments.count < maxAttachments else {
            vm.errorMessage = "Max \(maxAttachments) attachments per message"
            return
        }
        guard let data = try? Data(contentsOf: url) else {
            vm.errorMessage = "Could not read \(url.lastPathComponent)"
            return
        }
        guard data.count <= maxAttachmentBytes else {
            vm.errorMessage = "\(url.lastPathComponent) is too large (max 50 MB)"
            return
        }
        let mime = UTType(filenameExtension: ext)?.preferredMIMEType ?? "application/octet-stream"
        pendingAttachments.append(
            PendingChannelAttachment(data: data, filename: url.lastPathComponent, mimeType: mime)
        )
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
            vm.errorMessage = "No image on the clipboard — screenshot with ⌃⌘⇧4 first"
            return
        }
        guard pendingAttachments.count < maxAttachments else {
            vm.errorMessage = "Max \(maxAttachments) attachments per message"
            return
        }
        guard data.count <= maxAttachmentBytes else {
            vm.errorMessage = "Pasted image is too large (max 10 MB)"
            return
        }
        let stamp = Int(Date().timeIntervalSince1970)
        pendingAttachments.append(
            PendingChannelAttachment(data: data, filename: "pasted-\(stamp).png", mimeType: "image/png")
        )
    }
}
