import SwiftUI
import UniformTypeIdentifiers
import AppKit

/// Note editor: markdown text, the live-edit soft lock, AI revision review, and
/// version history. Two adjacent concerns live in siblings of this file:
///   • SectionEditorView+Comments.swift — anchored highlight-to-comment threads
///   • SectionEditorView+Toolbar.swift  — the markdown formatting toolbar
///   • SectionEditorView+Media.swift    — image / video upload + insert
///
/// State those extensions touch is internal rather than `private`, the same
/// arrangement `TaskViewerSheet` uses for its extension files.
struct SectionEditorView: View {
    let section: MWProjectSection
    let onSave: (String?, String?) -> Void
    /// Dismisses the editor back to the notes list. When non-nil a "← Notes"
    /// back button renders in the title row.
    var onBack: (() -> Void)? = nil
    /// Opens the email-this-note composer. When non-nil an envelope button
    /// renders next to back.
    var onEmail: (() -> Void)? = nil
    /// Current user id — for comment author attribution + delete-own gating.
    var currentUserId: String? = nil
    var onAcceptRevision: (() -> Void)? = nil
    var onRejectRevision: (() -> Void)? = nil
    var onRestore: ((String) -> Void)? = nil
    /// Project id for blog-media uploads. When nil the image / video toolbar
    /// buttons are disabled (callers that don't expose a project context can
    /// omit this).
    var projectId: String? = nil
    /// Reports caret position changes (anchor + head as character offsets)
    /// for real-time presence broadcasting. Throttling is the caller's job.
    var onCaretMove: ((Int, Int) -> Void)? = nil
    /// When non-nil, another collaborator holds this section's edit lock —
    /// render read-only with a live view of their edits + a banner.
    var lockedByName: String? = nil
    /// Live content streamed by the active editor, shown in watcher mode.
    var liveContent: SectionLiveContent? = nil
    /// The lock holder's caret, drawn in-text in watcher mode so you can see
    /// where they're working in the document (not a floating app pointer).
    var remoteCaret: RemoteCaretMark? = nil
    /// Claim / release the live-edit soft lock as the editor opens / closes.
    var onEditStart: (() -> Void)? = nil
    var onEditEnd: (() -> Void)? = nil
    /// Wrest the edit lock from the current holder (watcher → editor handoff).
    var onTakeOver: (() -> Void)? = nil
    /// Broadcast in-progress text to watchers (caller throttles).
    var onContentChange: ((_ title: String?, _ content: String) -> Void)? = nil

    @Environment(AppState.self) private var appState

    @State var title: String = ""
    @State var content: String = ""
    @State private var saveTimer: Timer?
    @State private var isSaved = false
    @State private var hasUnsavedChanges = false
    @State private var showPendingPreview = true
    @State var controller = MarkdownEditorController()
    /// Separate controller for the read-only watcher editor.
    @State var watcherController = MarkdownEditorController()
    @State var uploadStatus: String? = nil
    @State var uploadError: String? = nil
    /// Auto-release: the lock is dropped after a spell of inactivity so a
    /// watcher isn't blocked when the holder walks away. Re-acquired on the
    /// next edit. `releasedIdle` tracks that we let go while still on screen.
    @State private var idleTimer: Timer?
    @State private var releasedIdle = false
    private let idleReleaseSeconds: TimeInterval = 60

    // MARK: Comments state (behaviour in SectionEditorView+Comments.swift)
    @State var comments: [MWSectionComment] = []
    /// Live selection rect (editor-local) + char range, for the "add comment"
    /// affordance. Set from MarkdownTextEditor.onSelectionRectChange.
    @State var selRect: CGRect? = nil
    @State var selRange: (Int, Int)? = nil
    @State var composing = false
    @State var composeText = ""
    /// The compose card overlays the NSTextView editor; without explicitly
    /// driving first responder, the TextField never grabs the keyboard and
    /// typed text never lands (button stays disabled). Focus it when the card
    /// opens.
    @FocusState var composeFocused: Bool
    /// An opened thread (clicked highlight) + the rect to anchor its popover.
    @State var openThreadId: String? = nil
    @State var threadRect: CGRect? = nil
    @State var showAllComments = false

    // MARK: - Body

    var body: some View {
        VStack(spacing: 0) {
            topBar
            titleField
            Divider().opacity(0.2).padding(.horizontal, 20)
            editorArea
            footer
        }
        .background(Color(white: 0.11))
        .onAppear {
            title = section.title
            content = section.content ?? ""
            hasUnsavedChanges = false
            // Claim the soft lock. If denied, the parent flips `lockedByName`
            // and this view re-renders into watcher mode.
            onEditStart?()
            if lockedByName == nil { resetIdleTimer() }
        }
        .task(id: section.id) {
            // Opening the note = its comment notifications are seen → clear
            // them from the bell and the project tab badge.
            appState.markSectionSeen(sectionId: section.id)
            await loadComments()
        }
        .onChange(of: section.id) {
            // Different section — flush any pending save for the prior one.
            flushSaveIfDirty()
            title = section.title
            content = section.content ?? ""
            isSaved = false
            hasUnsavedChanges = false
            showPendingPreview = true
            releasedIdle = false
            resetIdleTimer()
            resetCommentUI()
        }
        .onChange(of: lockedByName) { _, newVal in
            if newVal != nil {
                // Someone took the lock from us → we drop to watcher. Preserve
                // our last edits. Don't release (we no longer hold it; release
                // is holder-guarded server-side anyway).
                flushSaveIfDirty()
                idleTimer?.invalidate()
            } else {
                // We just took over (watcher → editor): continue from the latest
                // streamed text, not the stale `section` prop.
                if let live = liveContent {
                    content = live.content
                    if let t = live.title { title = t }
                }
                releasedIdle = false
                resetIdleTimer()
            }
        }
        .onDisappear {
            idleTimer?.invalidate()
            flushSaveIfDirty()
            onEditEnd?()
        }
    }

    // MARK: - Chrome

    private var topBar: some View {
        HStack(spacing: 10) {
            if let onBack {
                Button {
                    flushSaveIfDirty()
                    onBack()
                } label: {
                    HStack(spacing: 4) {
                        Image(systemName: "chevron.left").font(.system(size: 11, weight: .semibold))
                        Text("Notes").font(.system(size: 12, weight: .medium))
                    }
                    .foregroundColor(.matcha500)
                }
                .buttonStyle(.plain)
                .keyboardShortcut("[", modifiers: .command)
                .help("Back to notes (⌘[)")
            }
            Spacer()
            allCommentsButton
            if let onEmail {
                Button {
                    flushSaveIfDirty()
                    onEmail()
                } label: {
                    HStack(spacing: 4) {
                        Image(systemName: "paperplane").font(.system(size: 11))
                        Text("Email").font(.system(size: 12, weight: .medium))
                    }
                    .foregroundColor(.white.opacity(0.85))
                }
                .buttonStyle(.plain)
                .help("Email this note")
            }
        }
        .padding(.horizontal, 20)
        .padding(.top, 12)
    }

    private var titleField: some View {
        TextField("Note title", text: $title)
            .textFieldStyle(.plain)
            .font(.system(size: 18, weight: .semibold))
            .foregroundColor(.white)
            .padding(.horizontal, 24)
            .padding(.top, 8)
            .padding(.bottom, 8)
            .disabled(lockedByName != nil)
            .onChange(of: title) {
                noteActivity()
                scheduleSave()
                onContentChange?(title.isEmpty ? nil : title, content)
            }
    }

    /// Either the read-only watcher view (someone else holds the lock) or the
    /// editable one. Both layer the comment affordances over the text.
    @ViewBuilder
    private var editorArea: some View {
        if let holder = lockedByName {
            // Watcher mode: another collaborator holds the lock. Show their
            // live edits in a read-only editor so their caret renders in-text
            // — no toolbar, no save.
            lockedWatcherBanner(holder)
            // Read-only, but still selectable — a watcher can highlight +
            // comment even while someone else holds the edit lock.
            GeometryReader { geo in
                ZStack(alignment: .topLeading) {
                    MarkdownTextEditor(
                        text: .constant(liveContent?.content ?? content),
                        controller: $watcherController,
                        isEditable: false,
                        remoteCarets: remoteCaret.map { [$0] } ?? [],
                        commentHighlights: commentHighlights,
                        onCommentTap: { id, rect in openCommentThread(id, at: rect) },
                        onSelectionRectChange: { rect, a, b in selectionChanged(rect, a, b) }
                    )
                    commentAffordances(width: geo.size.width)
                }
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
        } else {
            if section.hasPendingRevision {
                pendingRevisionBanner
            }

            formattingToolbar

            GeometryReader { geo in
                ZStack(alignment: .topLeading) {
                    MarkdownTextEditor(
                        text: $content,
                        controller: $controller,
                        onSelectionChange: { anchor, head in
                            onCaretMove?(anchor, head)
                        },
                        commentHighlights: commentHighlights,
                        onCommentTap: { id, rect in openCommentThread(id, at: rect) },
                        onSelectionRectChange: { rect, a, b in selectionChanged(rect, a, b) }
                    )
                    .onChange(of: content) {
                        noteActivity()
                        scheduleSave()
                        onContentChange?(title.isEmpty ? nil : title, content)
                    }
                    commentAffordances(width: geo.size.width)
                }
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
        }
    }

    private var footer: some View {
        HStack(spacing: 12) {
            Text("Markdown supported")
                .font(.system(size: 10))
                .foregroundColor(.secondary)
            if let status = uploadStatus {
                Text(status)
                    .font(.system(size: 10))
                    .foregroundColor(.matcha500)
            }
            if let err = uploadError {
                Text(err)
                    .font(.system(size: 10))
                    .foregroundColor(.red)
                    .lineLimit(1)
            }
            Spacer()
            // Hide restore while watching — restoring would clobber the
            // active editor's live work.
            if lockedByName == nil {
                historyMenu
            }
            if isSaved {
                Text("Saved")
                    .font(.system(size: 10, weight: .medium))
                    .foregroundColor(.matcha500)
                    .transition(.opacity)
            }
        }
        .padding(.horizontal, 24)
        .padding(.vertical, 8)
        .background(Color.zinc800.opacity(0.3))
    }

    private func lockedWatcherBanner(_ holder: String) -> some View {
        HStack(spacing: 6) {
            Image(systemName: "pencil.circle.fill")
                .font(.system(size: 11))
                .foregroundColor(.orange)
            Text("\(holder) is editing — live view, read-only")
                .font(.system(size: 11, weight: .medium))
                .foregroundColor(.orange)
            Spacer()
            if let onTakeOver {
                Button(action: onTakeOver) {
                    HStack(spacing: 4) {
                        Image(systemName: "hand.raised.fill").font(.system(size: 9))
                        Text("Take over").font(.system(size: 11, weight: .semibold))
                    }
                    .foregroundColor(.white)
                    .padding(.horizontal, 9)
                    .padding(.vertical, 3)
                    .background(Color.orange)
                    .cornerRadius(5)
                }
                .buttonStyle(.plain)
                .help("Take over editing — \(holder) drops to read-only")
            }
        }
        .padding(.horizontal, 24)
        .padding(.vertical, 8)
        .background(Color.orange.opacity(0.12))
    }

    // MARK: - Saving

    /// Fires an immediate synchronous-ish save if there are unsaved edits,
    /// bypassing the 1s debounce. Called on view disappear and section switch
    /// so user text is durable before any sibling action (chat send, tab
    /// change) can trigger an AI revision against stale content.
    private func flushSaveIfDirty() {
        saveTimer?.invalidate()
        saveTimer = nil
        guard hasUnsavedChanges else { return }
        let t = title.isEmpty ? nil : title
        onSave(t, content)
        hasUnsavedChanges = false
    }

    private func scheduleSave() {
        isSaved = false
        hasUnsavedChanges = true
        saveTimer?.invalidate()
        saveTimer = Timer.scheduledTimer(withTimeInterval: 1.0, repeats: false) { _ in
            let t = title.isEmpty ? nil : title
            let c = content
            onSave(t, c)
            hasUnsavedChanges = false
            Task { @MainActor in
                withAnimation { isSaved = true }
                try? await Task.sleep(for: .seconds(2))
                withAnimation { isSaved = false }
            }
        }
    }

    // MARK: - Edit-lock idle release

    /// Mark editor activity: re-acquire the lock if we'd released it for idle,
    /// then restart the idle countdown. No-op in watcher mode.
    private func noteActivity() {
        guard lockedByName == nil else { return }
        if releasedIdle {
            onEditStart?()
            releasedIdle = false
        }
        resetIdleTimer()
    }

    private func resetIdleTimer() {
        idleTimer?.invalidate()
        guard lockedByName == nil else { return }
        idleTimer = Timer.scheduledTimer(withTimeInterval: idleReleaseSeconds, repeats: false) { _ in
            Task { @MainActor in
                guard lockedByName == nil, !releasedIdle else { return }
                onEditEnd?()
                releasedIdle = true
            }
        }
    }

    // MARK: - AI revision + history

    private var pendingRevisionBanner: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                Image(systemName: "sparkles")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundColor(.matcha500)
                Text("AI suggestion")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundColor(.matcha500)
                if let summary = section.pendingChangeSummary, !summary.isEmpty {
                    Text("— \(summary)")
                        .font(.system(size: 11))
                        .foregroundColor(.secondary)
                        .lineLimit(2)
                }
                Spacer()
                Button {
                    showPendingPreview.toggle()
                } label: {
                    Image(systemName: showPendingPreview ? "chevron.up" : "chevron.down")
                        .font(.system(size: 10))
                        .foregroundColor(.secondary)
                }
                .buttonStyle(.plain)
                Button("Reject") { onRejectRevision?() }
                    .font(.system(size: 11, weight: .medium))
                    .buttonStyle(.plain)
                    .foregroundColor(.secondary)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 4)
                    .background(Color.zinc800)
                    .cornerRadius(5)
                Button("Accept") { onAcceptRevision?() }
                    .font(.system(size: 11, weight: .semibold))
                    .buttonStyle(.plain)
                    .foregroundColor(.white)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 4)
                    .background(Color.matcha600)
                    .cornerRadius(5)
            }

            if showPendingPreview, let pending = section.pendingRevision, !pending.isEmpty {
                ScrollView {
                    Text(pending)
                        .font(.system(size: 12, design: .monospaced))
                        .foregroundColor(Color(white: 0.85))
                        .textSelection(.enabled)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(10)
                }
                .frame(maxHeight: 180)
                .background(Color.black.opacity(0.25))
                .cornerRadius(6)
            }
        }
        .padding(.horizontal, 20)
        .padding(.vertical, 10)
        .background(Color.matcha600.opacity(0.08))
        .overlay(
            Rectangle()
                .frame(height: 1)
                .foregroundColor(Color.matcha600.opacity(0.3)),
            alignment: .bottom
        )
    }

    @ViewBuilder
    private var historyMenu: some View {
        let entries = section.history ?? []
        if !entries.isEmpty {
            Menu {
                ForEach(entries.reversed()) { entry in
                    Button {
                        onRestore?(entry.content)
                    } label: {
                        // Prefer the author's name; older snapshots without
                        // attribution fall back to the source category.
                        Text("\(formatHistoryTime(entry.at)) · \(entry.authorName ?? entry.source ?? "user") (\(entry.content.split(separator: " ").count) words)")
                    }
                }
            } label: {
                HStack(spacing: 4) {
                    Image(systemName: "clock.arrow.circlepath").font(.system(size: 10))
                    Text("History (\(entries.count))").font(.system(size: 10, weight: .medium))
                }
                .foregroundColor(.secondary)
                .padding(.horizontal, 7)
                .padding(.vertical, 3)
                .background(Color.zinc800)
                .cornerRadius(5)
            }
            .menuStyle(.borderlessButton)
            .fixedSize()
            .help("Restore an earlier version of this section")
        }
    }

    private func formatHistoryTime(_ iso: String) -> String {
        let isoFmt = ISO8601DateFormatter()
        isoFmt.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let date = isoFmt.date(from: iso) ?? ISO8601DateFormatter().date(from: iso)
        guard let d = date else { return iso }
        let fmt = DateFormatter()
        fmt.dateFormat = "MMM d, h:mm a"
        return fmt.string(from: d)
    }
}
