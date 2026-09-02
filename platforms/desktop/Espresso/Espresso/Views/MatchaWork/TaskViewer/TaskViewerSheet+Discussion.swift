import SwiftUI

// MARK: - Discussion: the in-ticket Q&A thread and its composer
//
// Split out of TaskViewerSheet+Sections.swift.

extension TaskViewerSheet {

    /// The in-ticket Q&A thread: a note composer plus the activity notes,
    /// newest-first. Always visible in every column so clarifying questions
    /// are one click away. Posting a note bells the other participants.
    @ViewBuilder
    var discussionSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            discussionHeader

            if !isAddingAutoPRContext {
                noteComposer
            }

            // One combined thread, newest-first (current-round comments land on
            // top). Each row carries a Round-N chip and prior-round comments are
            // dimmed, so it's never ambiguous which round a comment is from.
            if !notes.isEmpty {
                ForEach(Array(notes.reversed())) { note in
                    NoteRow(
                        entry: note,
                        files: attachments,
                        noteRound: roundIndex(forCreatedAt: note.createdAt),
                        currentRound: currentRound,
                        onPreview: { previewFile = $0 },
                        onReply: {
                            replyingToNote = note
                            isNoteFieldFocused = true
                        }
                    )
                }
            } else if !loadingHistory {
                Text("No comments yet — ask a question to start the thread.")
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
                    .padding(.vertical, 4)
            }
        }
    }

    @ViewBuilder
    private var discussionHeader: some View {
        if appState.isGraphite {
            HStack(spacing: 8) {
                asciiRule("DISCUSSION")
                if loadingHistory { ProgressView().controlSize(.small) }
                if currentRound > 1 { roundScopePill }
            }
        } else {
            HStack(spacing: 6) {
                Image(systemName: "bubble.left.and.bubble.right")
                    .font(.system(size: 10))
                    .foregroundColor(.mwInkStrong)
                Text("DISCUSSION")
                    .font(.system(size: 9, weight: .semibold))
                    .foregroundColor(.secondary)
                    .tracking(0.5)
                Text("Ask & answer clarifications")
                    .font(.system(size: 9))
                    .foregroundColor(.secondary.opacity(0.7))
                if loadingHistory {
                    ProgressView().controlSize(.small)
                }
                Spacer()
                if currentRound > 1 {
                    roundScopePill
                }
            }
        }
    }

    // MARK: - Composer

    var canSubmitNote: Bool {
        let hasText = !newNote.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        return hasText || !pendingAttachments.isEmpty
    }

    /// Heuristic: does this note text read like an actionable to-do? Only nudges
    /// ("add as subtask?") — never blocks adding a normal note. Imperative verb
    /// at the start, or "need to / should / todo / checkbox" phrasing.
    func looksLikeSubtask(_ s: String) -> Bool {
        let t = s.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard t.count >= 4 else { return false }
        if t.contains("need to") || t.contains("should ") || t.hasPrefix("todo")
            || t.contains("to-do") || t.hasPrefix("- ") || t.hasPrefix("[ ]") { return true }
        return Self.subtaskVerbPrefixes.contains(where: { t.hasPrefix($0) })
    }

    /// Imperative openers that mark a note as an actionable to-do. Static so the
    /// array isn't rebuilt on every keystroke — `looksLikeSubtask` runs from the
    /// composer's body, i.e. on each character typed.
    static let subtaskVerbPrefixes = [
        "add ", "implement ", "fix ", "create ", "build ", "write ",
        "test ", "update ", "remove ", "refactor ", "verify ", "ensure ",
        "make ", "set up ", "handle ", "validate ", "document ",
        "investigate ", "check ", "wire ", "hook up ", "review ",
    ]

    var noteComposer: some View {
        VStack(alignment: .leading, spacing: 6) {
            if isAddingAutoPRContext {
                autoPRContextReplyBanner
            } else if let replying = replyingToNote {
                replyingToBanner(replying)
            }
            HStack(spacing: 6) {
                TextField(
                    isAddingAutoPRContext
                        ? "Add evidence or explain what AutoPR missed…"
                        : (replyingToNote == nil ? "Add a note…" : "Write a reply…"),
                    text: $newNote
                )
                    .textFieldStyle(.plain)
                    .font(.system(size: 12))
                    .foregroundColor(appState.themeText)
                    .padding(7)
                    .background(appState.themeText.opacity(0.07))
                    .cornerRadius(5)
                    .focused($isNoteFieldFocused)
                    .onSubmit { Task { await submitNote() } }
                Button {
                    attachFileFromDisk()
                } label: {
                    Image(systemName: "paperclip")
                        .font(.system(size: 12))
                        .foregroundColor(.secondary)
                }
                .buttonStyle(.plain)
                .help("Attach a file (image / PDF)")
                Button {
                    attachImageFromClipboard()
                } label: {
                    Image(systemName: "doc.on.clipboard")
                        .font(.system(size: 12))
                        .foregroundColor(.secondary)
                }
                .buttonStyle(.plain)
                .help("Paste screenshot from clipboard")
                Button {
                    Task { await submitNote() }
                } label: {
                    if addingNote {
                        ProgressView().controlSize(.small)
                    } else {
                        Text(isAddingAutoPRContext ? "Submit" : "Add")
                            .font(.system(size: 12, weight: .semibold))
                            .foregroundColor(canSubmitNote ? .mwInkStrong : .secondary)
                    }
                }
                .buttonStyle(.plain)
                .disabled(!canSubmitNote || addingNote)
            }

            // Self-check: people often type an actionable to-do as a note. When
            // the text reads like a task, offer to capture it as a subtask instead.
            if !isAddingAutoPRContext && looksLikeSubtask(newNote) {
                subtaskNudge
            }

            if let error = autoPRContextError, isAddingAutoPRContext {
                Text(error)
                    .font(.system(size: 10))
                    .foregroundColor(.mwAttention)
                    .fixedSize(horizontal: false, vertical: true)
            }

            if !pendingAttachments.isEmpty {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 6) {
                        ForEach(pendingAttachments) { att in
                            PendingAttachmentChip(attachment: att) {
                                pendingAttachments.removeAll { $0.id == att.id }
                            }
                        }
                    }
                }
            }
        }
    }

    private var autoPRContextReplyBanner: some View {
        HStack(spacing: 6) {
            Rectangle()
                .fill(Color.mwInkStrong)
                .frame(width: 2)
                .cornerRadius(1)
            VStack(alignment: .leading, spacing: 1) {
                Text("Additional context for AUTO SETUP")
                    .font(.system(size: 9, weight: .semibold))
                    .foregroundColor(.mwInkStrong)
                Text(autoSetupStatus.label)
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
                    .lineLimit(1)
            }
            Spacer(minLength: 0)
            Button {
                isAddingAutoPRContext = false
                autoPRContextError = nil
            } label: {
                Image(systemName: "xmark.circle.fill")
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
            }
            .buttonStyle(.plain)
            .help("Cancel additional context")
        }
        .padding(.horizontal, 7)
        .padding(.vertical, 5)
        .background(appState.themeText.opacity(0.07))
        .cornerRadius(5)
    }

    private var subtaskNudge: some View {
        HStack(spacing: 6) {
            Image(systemName: "checklist").font(.system(size: 9)).foregroundColor(.mwInkStrong)
            Text("Looks like a to-do — add it as a subtask instead?")
                .font(.system(size: 10)).foregroundColor(appState.themeTextSecondary)
            Button("Add as subtask") {
                let t = newNote.trimmingCharacters(in: .whitespacesAndNewlines)
                Task { await viewModel.addSubtask(taskId: task.id, title: t) }
                newNote = ""
            }
            .buttonStyle(.plain).font(.system(size: 10, weight: .semibold)).foregroundColor(.mwInkStrong)
            Spacer(minLength: 0)
        }
        .padding(.leading, 2)
    }

    /// "Replying to {name}: {excerpt}" chip shown above the composer while a
    /// reply is in flight. Tapping the × clears the reply target.
    @ViewBuilder
    func replyingToBanner(_ note: MWTaskHistoryEntry) -> some View {
        let name = note.actorName?.isEmpty == false ? note.actorName! : "comment"
        let excerpt = (note.metadata?["body"] ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .replacingOccurrences(of: "\n", with: " ")
        HStack(spacing: 6) {
            Rectangle()
                .fill(Color.mwInkStrong)
                .frame(width: 2)
                .cornerRadius(1)
            VStack(alignment: .leading, spacing: 1) {
                Text("Replying to \(name)")
                    .font(.system(size: 9, weight: .semibold))
                    .foregroundColor(.mwInkStrong)
                if !excerpt.isEmpty {
                    Text(excerpt)
                        .font(.system(size: 10))
                        .foregroundColor(.secondary)
                        .lineLimit(1)
                }
            }
            Spacer(minLength: 0)
            Button {
                replyingToNote = nil
            } label: {
                Image(systemName: "xmark.circle.fill")
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
            }
            .buttonStyle(.plain)
            .help("Cancel reply")
        }
        .padding(.horizontal, 7)
        .padding(.vertical, 5)
        .background(appState.themeText.opacity(0.07))
        .cornerRadius(5)
    }
}
