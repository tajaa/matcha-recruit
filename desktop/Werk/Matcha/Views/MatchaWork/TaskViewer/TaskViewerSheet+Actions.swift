import SwiftUI
import AppKit
import UniformTypeIdentifiers

// MARK: - Actions (history loading, attachments, note/round/reject submit, copy)

extension TaskViewerSheet {
    /// Sheet-callback path for starting a new round. Mirrors `submitNote`:
    /// uploads pending attachments first (so file ids exist before being
    /// referenced in the kick-off note), then calls the rounds endpoint.
    /// Returns true on success so the sheet can dismiss + clear state.
    @MainActor
    func submitNewRound(
        suggestedFix: String,
        body: String,
        pending: [PendingAttachment],
        completedSubtaskIds: [String]
    ) async -> Bool {
        guard let pid = viewModel.project?.id else { return false }
        // Persist the completions the user just acknowledged BEFORE opening the
        // round, so the backend archives those items on the current round and
        // only rolls the still-unfinished ones forward into the new round.
        for sid in completedSubtaskIds {
            await viewModel.toggleSubtask(taskId: task.id, subtaskId: sid, isDone: true)
        }
        var uploadedIds: [String] = []
        for att in pending {
            guard let id = await viewModel.uploadTaskFile(
                taskId: task.id,
                data: att.data,
                filename: att.filename,
                mimeType: att.mimeType
            ) else {
                return false
            }
            uploadedIds.append(id)
        }
        do {
            try await MatchaWorkService.shared.startNewRound(
                projectId: pid,
                taskId: task.id,
                suggestedFixTitle: suggestedFix,
                body: body.isEmpty ? nil : body,
                attachmentIds: uploadedIds.isEmpty ? nil : uploadedIds
            )
            // Reload BOTH history (for round_started + activity rows) and the
            // subtask list (for the headline subtask just created) so the
            // checklist + rounds feed both reflect the new state.
            await loadHistory()
            await viewModel.loadSubtasks(taskId: task.id)
            showingNewRoundSheet = false
            return true
        } catch {
            return false
        }
    }

    func loadHistory() async {
        guard let pid = viewModel.project?.id else { return }
        loadingHistory = true
        defer { loadingHistory = false }
        if let rows = try? await MatchaWorkService.shared.fetchTaskHistory(
            projectId: pid, taskId: task.id
        ) {
            history = rows
            // Opening the ticket = the user has seen what's new (this round's
            // content is inline). Clear the card's unviewed-updates badge.
            let counted = rows
                .filter { TicketUpdatesStore.countedEventTypes.contains($0.eventType) }
                .map(\.id)
            TicketUpdatesStore.shared.markAllViewed(taskId: task.id, eventIds: counted)
        }
        historyLoaded = true
    }

    func attachFileFromDisk() {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = false
        panel.allowsMultipleSelection = true
        panel.allowedContentTypes = [.image, .pdf]
        panel.begin { resp in
            guard resp == .OK else { return }
            for url in panel.urls {
                guard let data = try? Data(contentsOf: url) else { continue }
                let filename = url.lastPathComponent
                let mime = mimeTypeFor(filename: filename, fallback: "application/octet-stream")
                pendingAttachments.append(PendingAttachment(data: data, filename: filename, mimeType: mime))
            }
        }
    }

    func attachImageFromClipboard() {
        let pb = NSPasteboard.general
        // Prefer PNG (lossless screenshot), then TIFF, then JPEG. Cmd+Shift+4
        // screenshots-to-clipboard land as PNG; Cmd+C on an image in Preview
        // typically lands as TIFF.
        if let png = pb.data(forType: .png) {
            pendingAttachments.append(PendingAttachment(
                data: png,
                filename: clipboardScreenshotName(ext: "png"),
                mimeType: "image/png"
            ))
            return
        }
        if let tiff = pb.data(forType: .tiff),
           let rep = NSBitmapImageRep(data: tiff),
           let png = rep.representation(using: .png, properties: [:]) {
            pendingAttachments.append(PendingAttachment(
                data: png,
                filename: clipboardScreenshotName(ext: "png"),
                mimeType: "image/png"
            ))
            return
        }
        let jpegType = NSPasteboard.PasteboardType(UTType.jpeg.identifier)
        if let jpeg = pb.data(forType: jpegType) {
            pendingAttachments.append(PendingAttachment(
                data: jpeg,
                filename: clipboardScreenshotName(ext: "jpg"),
                mimeType: "image/jpeg"
            ))
            return
        }
    }

    func clipboardScreenshotName(ext: String) -> String {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd-HHmmss"
        return "screenshot-\(f.string(from: Date())).\(ext)"
    }

    func mimeTypeFor(filename: String, fallback: String) -> String {
        let ext = (filename as NSString).pathExtension.lowercased()
        if let ut = UTType(filenameExtension: ext),
           let mime = ut.preferredMIMEType { return mime }
        return fallback
    }

    func submitSubtask() {
        let text = newSubtask.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, !addingSubtask else { return }
        addingSubtask = true
        Task {
            await viewModel.addSubtask(taskId: task.id, title: text)
            await MainActor.run { newSubtask = ""; addingSubtask = false }
        }
    }

    func submitNote() async {
        let text = newNote.trimmingCharacters(in: .whitespacesAndNewlines)
        let pending = pendingAttachments
        guard (canSubmitNote), let pid = viewModel.project?.id, !addingNote else { return }
        addingNote = true
        defer { addingNote = false }

        // Upload pending attachments first; collect ids. A single upload
        // failure aborts so we never post a note with dangling references.
        var uploadedIds: [String] = []
        for att in pending {
            guard let id = await viewModel.uploadTaskFile(
                taskId: task.id,
                data: att.data,
                filename: att.filename,
                mimeType: att.mimeType
            ) else {
                // viewModel.errorMessage was set; keep text + chips so the
                // user can retry.
                return
            }
            uploadedIds.append(id)
        }

        do {
            try await MatchaWorkService.shared.logTaskActivity(
                projectId: pid, taskId: task.id, kind: "note", body: text,
                attachmentIds: uploadedIds.isEmpty ? nil : uploadedIds,
                replyTo: replyingToNote?.id
            )
            newNote = ""
            pendingAttachments = []
            replyingToNote = nil
            await loadHistory()
        } catch {
            // Best-effort; leave the text in place so the user can retry.
            // Note: attachments were already uploaded and persisted on the
            // task — they show up under ATTACHMENTS even if the activity
            // POST failed.
        }
    }

    func submitReject() async {
        let note = rejectNote.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !note.isEmpty, !submitting else { return }
        submitting = true
        let ok = await viewModel.rejectTask(id: task.id, note: note)
        submitting = false
        if ok {
            isRejecting = false
            rejectNote = ""
            onClose()
        }
    }

    /// Reviewer approves out of review → done with an optional sign-off note.
    /// Mirrors submitReject: only closes the sheet once the move actually lands,
    /// so a failure surfaces instead of silently vanishing.
    func submitApprove() async {
        guard !submitting else { return }
        submitting = true
        let note = approveNote.trimmingCharacters(in: .whitespacesAndNewlines)
        let ok = await viewModel.approveTask(taskId: task.id, note: note.isEmpty ? nil : note)
        submitting = false
        if ok {
            isApproving = false
            approveNote = ""
            onClose()
        }
    }

    /// Copies the ticket as a single TEXT blob tuned for Claude Code: title,
    /// status, description, checklist (subtasks), and the screenshots written
    /// out as LOCAL file paths Claude Code can open with its Read tool.
    ///
    /// Deliberately text-only — no image bytes on the clipboard. Claude Code
    /// (and most CLIs) grab image data whenever it's present and drop the text,
    /// which loses the ticket context. Local paths sidestep that: one paste
    /// carries the full ticket AND loadable screenshots. (These are real local
    /// files, unlike the dead CloudFront URLs the export used to emit.)
    @MainActor
    func copyTicketToClipboard() async {
        isCopying = true

        // Download up to 6 image attachments and write them to a per-task temp
        // dir so their paths are real + readable. Only successfully-written
        // files contribute a path (never list an unreadable one).
        let images = Array(attachments.filter { $0.isImage }.prefix(6))
        let tmpDir = FileManager.default.temporaryDirectory
            .appendingPathComponent("werk-ticket-\(task.id)", isDirectory: true)
        try? FileManager.default.createDirectory(at: tmpDir, withIntermediateDirectories: true)

        var screenshotPaths: [String] = []
        for (idx, img) in images.enumerated() {
            guard let url = URL(string: img.storageUrl),
                  let (data, _) = try? await URLSession.shared.data(from: url) else { continue }
            let safeName = img.filename.isEmpty ? "image-\(idx).png" : img.filename
            let fileURL = tmpDir.appendingPathComponent("\(idx)-\(safeName)")
            if (try? data.write(to: fileURL)) != nil {
                screenshotPaths.append(fileURL.path)
            }
        }

        let markdown = TaskClipboardExporter.markdown(
            for: task,
            attachments: attachments,
            subtasks: subtasks,
            screenshotPaths: screenshotPaths,
        )

        let board = NSPasteboard.general
        board.clearContents()
        board.setString(markdown, forType: .string)

        isCopying = false
        didCopy = true
        Task {
            try? await Task.sleep(for: .milliseconds(1500))
            await MainActor.run { didCopy = false }
        }
    }
}
