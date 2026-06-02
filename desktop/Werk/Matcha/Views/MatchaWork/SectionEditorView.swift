import SwiftUI
import UniformTypeIdentifiers
import AppKit

struct SectionEditorView: View {
    let section: MWProjectSection
    let onSave: (String?, String?) -> Void
    /// Dismisses the editor back to the notes list. When non-nil a "← Notes"
    /// back button renders in the title row.
    var onBack: (() -> Void)? = nil
    /// Opens the email-this-note composer. When non-nil an envelope button
    /// renders next to back.
    var onEmail: (() -> Void)? = nil
    /// Opens the note comments panel. When non-nil a comment button renders in
    /// the title row.
    var onComments: (() -> Void)? = nil
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

    @State private var title: String = ""
    @State private var content: String = ""
    @State private var saveTimer: Timer?
    @State private var isSaved = false
    @State private var hasUnsavedChanges = false
    @State private var showPendingPreview = true
    @State private var controller = MarkdownEditorController()
    /// Separate controller for the read-only watcher editor.
    @State private var watcherController = MarkdownEditorController()
    @State private var uploadStatus: String? = nil
    @State private var uploadError: String? = nil
    /// Auto-release: the lock is dropped after a spell of inactivity so a
    /// watcher isn't blocked when the holder walks away. Re-acquired on the
    /// next edit. `releasedIdle` tracks that we let go while still on screen.
    @State private var idleTimer: Timer?
    @State private var releasedIdle = false
    private let idleReleaseSeconds: TimeInterval = 60

    var body: some View {
        VStack(spacing: 0) {
            // Back bar + title
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
                if let onComments {
                    Button {
                        onComments()
                    } label: {
                        HStack(spacing: 4) {
                            Image(systemName: "bubble.left.and.bubble.right").font(.system(size: 11))
                            Text("Comments").font(.system(size: 12, weight: .medium))
                        }
                        .foregroundColor(.white.opacity(0.85))
                    }
                    .buttonStyle(.plain)
                    .help("Comments on this note")
                }
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

            Divider().opacity(0.2).padding(.horizontal, 20)

            if let holder = lockedByName {
                // Watcher mode: another collaborator holds the lock. Show their
                // live edits in a read-only editor so their caret renders in-text
                // — no toolbar, no save.
                lockedWatcherBanner(holder)
                MarkdownTextEditor(
                    text: .constant(liveContent?.content ?? content),
                    controller: $watcherController,
                    isEditable: false,
                    remoteCarets: remoteCaret.map { [$0] } ?? []
                )
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
            } else {
                if section.hasPendingRevision {
                    pendingRevisionBanner
                }

                formattingToolbar

                // Content editor
                MarkdownTextEditor(
                    text: $content,
                    controller: $controller,
                    onSelectionChange: { anchor, head in
                        onCaretMove?(anchor, head)
                    }
                )
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .onChange(of: content) {
                        noteActivity()
                        scheduleSave()
                        onContentChange?(title.isEmpty ? nil : title, content)
                    }
            }

            // Footer
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

    // MARK: - Formatting toolbar

    @ViewBuilder
    private var formattingToolbar: some View {
        HStack(spacing: 3) {
            toolbarButton("B", bold: true, help: "Bold") {
                controller.wrapSelection(left: "**", right: "**", placeholder: "bold")
            }
            toolbarButton("I", italic: true, help: "Italic") {
                controller.wrapSelection(left: "*", right: "*", placeholder: "italic")
            }
            toolbarButton("H1", help: "Heading 1") {
                controller.prefixLines(with: "# ")
            }
            toolbarButton("H2", help: "Heading 2") {
                controller.prefixLines(with: "## ")
            }
            toolbarIcon("list.bullet", help: "Bulleted list") {
                controller.prefixLines(with: "- ")
            }
            toolbarIcon("list.number", help: "Numbered list") {
                controller.prefixLines(with: "1. ")
            }
            toolbarIcon("text.quote", help: "Quote") {
                controller.prefixLines(with: "> ")
            }
            toolbarIcon("chevron.left.forwardslash.chevron.right", help: "Inline code") {
                controller.wrapSelection(left: "`", right: "`", placeholder: "code")
            }
            toolbarIcon("link", help: "Link") {
                controller.wrapSelection(left: "[", right: "](https://)", placeholder: "text")
            }
            Divider().frame(height: 14).padding(.horizontal, 2)
            toolbarButton("1×", help: "Single line spacing") {
                controller.wrapSelection(
                    left: "<div style=\"line-height:1.0\">\n",
                    right: "\n</div>",
                    placeholder: "text"
                )
            }
            toolbarButton("1.5", help: "1.5 line spacing") {
                controller.wrapSelection(
                    left: "<div style=\"line-height:1.5\">\n",
                    right: "\n</div>",
                    placeholder: "text"
                )
            }
            toolbarButton("2×", help: "Double line spacing") {
                controller.wrapSelection(
                    left: "<div style=\"line-height:2.0\">\n",
                    right: "\n</div>",
                    placeholder: "text"
                )
            }
            Divider().frame(height: 14).padding(.horizontal, 2)
            toolbarIcon("photo", help: projectId == nil ? "Image (no project)" : "Insert image (max 50 MB)") {
                pickMedia(kind: .image)
            }
            .disabled(projectId == nil)
            toolbarIcon("video", help: projectId == nil ? "Video (no project)" : "Insert video (max 50 MB)") {
                pickMedia(kind: .video)
            }
            .disabled(projectId == nil)
            Spacer()
        }
        .padding(.horizontal, 20)
        .padding(.vertical, 6)
        .background(Color.zinc800.opacity(0.35))
        .overlay(
            Rectangle().frame(height: 1).foregroundColor(.white.opacity(0.08)),
            alignment: .bottom
        )
    }

    @ViewBuilder
    private func toolbarButton(_ label: String, bold: Bool = false, italic: Bool = false, help: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(label)
                .font(.system(size: 12, weight: bold ? .bold : .medium, design: .default))
                .italic(italic)
                .frame(width: 26, height: 22)
                .foregroundColor(.white)
                .background(Color.zinc800)
                .cornerRadius(4)
        }
        .buttonStyle(.plain)
        .help(help)
    }

    @ViewBuilder
    private func toolbarIcon(_ systemName: String, help: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: systemName)
                .font(.system(size: 11))
                .frame(width: 26, height: 22)
                .foregroundColor(.white)
                .background(Color.zinc800)
                .cornerRadius(4)
        }
        .buttonStyle(.plain)
        .help(help)
    }

    // MARK: - Media upload

    private enum MediaKind { case image, video }

    private func pickMedia(kind: MediaKind) {
        guard projectId != nil else { return }
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = false
        panel.canChooseDirectories = false
        panel.canChooseFiles = true
        switch kind {
        case .image:
            panel.allowedContentTypes = [.png, .jpeg, .gif, .webP, .heic, .svg]
        case .video:
            panel.allowedContentTypes = [.movie, .video, .quickTimeMovie, .mpeg4Movie]
        }
        panel.begin { response in
            guard response == .OK, let url = panel.urls.first else { return }
            Task { await uploadAndInsert(url: url, kind: kind) }
        }
    }

    private func uploadAndInsert(url: URL, kind: MediaKind) async {
        guard let pid = projectId else { return }
        guard let data = try? Data(contentsOf: url) else {
            await MainActor.run { uploadError = "Couldn't read file" }
            return
        }
        if data.count > 50 * 1024 * 1024 {
            await MainActor.run { uploadError = "File exceeds 50 MB" }
            return
        }
        let ext = url.pathExtension.lowercased()
        let mime = UTType(filenameExtension: ext)?.preferredMIMEType ?? (kind == .image ? "image/png" : "video/mp4")
        await MainActor.run {
            uploadStatus = "Uploading \(url.lastPathComponent)…"
            uploadError = nil
        }
        do {
            let uploaded = try await MatchaWorkService.shared.uploadBlogMedia(
                projectId: pid,
                file: (data: data, filename: url.lastPathComponent, mimeType: mime)
            )
            await MainActor.run {
                let snippet: String
                switch kind {
                case .image:
                    snippet = "![\(url.deletingPathExtension().lastPathComponent)](\(uploaded.url))"
                case .video:
                    snippet = "<video src=\"\(uploaded.url)\" controls width=\"100%\"></video>"
                }
                controller.insertBlock(snippet)
                uploadStatus = nil
            }
        } catch {
            await MainActor.run {
                uploadStatus = nil
                uploadError = error.localizedDescription
            }
        }
    }
}

// MARK: - Email this note

/// Composer sheet that emails a note as a PDF attachment. Recipients are a
/// mix of project collaborators (toggle list) and free-text addresses. Sends
/// immediately via the backend; no scheduling in v1.
struct NoteEmailComposer: View {
    let projectId: String
    let section: MWProjectSection
    let collaborators: [MWProjectCollaborator]
    var onClose: () -> Void

    @State private var selectedEmails: Set<String> = []
    @State private var extraInput: String = ""
    @State private var extraEmails: [String] = []
    @State private var subject: String = ""
    @State private var message: String = ""
    @State private var sending = false
    @State private var resultText: String? = nil
    @State private var isError = false

    private var allRecipients: [String] {
        // selected collaborator emails + free-text, lowercased + deduped.
        var seen = Set<String>()
        var out: [String] = []
        for e in selectedEmails.map({ $0.lowercased() }) + extraEmails.map({ $0.lowercased() }) {
            if !e.isEmpty && !seen.contains(e) { seen.insert(e); out.append(e) }
        }
        return out
    }

    private func looksLikeEmail(_ s: String) -> Bool {
        let t = s.trimmingCharacters(in: .whitespaces)
        guard let at = t.firstIndex(of: "@"), at != t.startIndex else { return false }
        let domain = t[t.index(after: at)...]
        return domain.contains(".") && !domain.hasSuffix(".")
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Text("Email note").font(.system(size: 15, weight: .semibold)).foregroundColor(.white)
                Spacer()
                Button { onClose() } label: {
                    Image(systemName: "xmark").font(.system(size: 12, weight: .semibold)).foregroundColor(.secondary)
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, 20)
            .padding(.vertical, 14)

            Divider().opacity(0.2)

            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    // Collaborators
                    if !collaborators.isEmpty {
                        VStack(alignment: .leading, spacing: 6) {
                            Text("COLLABORATORS").font(.system(size: 10, weight: .semibold)).foregroundColor(.secondary)
                            ForEach(collaborators) { c in
                                Button {
                                    if selectedEmails.contains(c.email) { selectedEmails.remove(c.email) }
                                    else { selectedEmails.insert(c.email) }
                                } label: {
                                    HStack(spacing: 8) {
                                        Image(systemName: selectedEmails.contains(c.email) ? "checkmark.circle.fill" : "circle")
                                            .font(.system(size: 13))
                                            .foregroundColor(selectedEmails.contains(c.email) ? .matcha500 : .secondary)
                                        VStack(alignment: .leading, spacing: 1) {
                                            Text(c.name).font(.system(size: 12, weight: .medium)).foregroundColor(.white)
                                            Text(c.email).font(.system(size: 10)).foregroundColor(.secondary)
                                        }
                                        Spacer()
                                    }
                                    .contentShape(Rectangle())
                                }
                                .buttonStyle(.plain)
                            }
                        }
                    }

                    // Free-text recipients
                    VStack(alignment: .leading, spacing: 6) {
                        Text("OTHER RECIPIENTS").font(.system(size: 10, weight: .semibold)).foregroundColor(.secondary)
                        if !extraEmails.isEmpty {
                            FlowChips(items: extraEmails) { email in
                                extraEmails.removeAll { $0 == email }
                            }
                        }
                        HStack(spacing: 6) {
                            TextField("name@example.com", text: $extraInput, onCommit: addExtra)
                                .textFieldStyle(.plain)
                                .font(.system(size: 12))
                                .foregroundColor(.white)
                                .padding(.horizontal, 10).padding(.vertical, 7)
                                .background(Color.zinc800).cornerRadius(6)
                            Button("Add", action: addExtra)
                                .buttonStyle(.plain)
                                .font(.system(size: 11, weight: .medium))
                                .foregroundColor(.white)
                                .padding(.horizontal, 12).padding(.vertical, 7)
                                .background(looksLikeEmail(extraInput) ? Color.matcha600 : Color.zinc800)
                                .cornerRadius(6)
                                .disabled(!looksLikeEmail(extraInput))
                        }
                    }

                    // Subject
                    VStack(alignment: .leading, spacing: 6) {
                        Text("SUBJECT").font(.system(size: 10, weight: .semibold)).foregroundColor(.secondary)
                        TextField(section.title, text: $subject)
                            .textFieldStyle(.plain)
                            .font(.system(size: 12))
                            .foregroundColor(.white)
                            .padding(.horizontal, 10).padding(.vertical, 7)
                            .background(Color.zinc800).cornerRadius(6)
                    }

                    // Cover message
                    VStack(alignment: .leading, spacing: 6) {
                        Text("MESSAGE (OPTIONAL)").font(.system(size: 10, weight: .semibold)).foregroundColor(.secondary)
                        TextEditor(text: $message)
                            .font(.system(size: 12))
                            .foregroundColor(.white)
                            .scrollContentBackground(.hidden)
                            .frame(height: 90)
                            .padding(.horizontal, 6).padding(.vertical, 4)
                            .background(Color.zinc800).cornerRadius(6)
                    }

                    HStack(spacing: 6) {
                        Image(systemName: "paperclip").font(.system(size: 10)).foregroundColor(.secondary)
                        Text("“\(section.title)” attached as a PDF").font(.system(size: 10)).foregroundColor(.secondary)
                    }
                }
                .padding(20)
            }

            Divider().opacity(0.2)

            HStack {
                if let resultText {
                    Text(resultText)
                        .font(.system(size: 11, weight: .medium))
                        .foregroundColor(isError ? .red : .matcha500)
                        .lineLimit(2)
                }
                Spacer()
                Button("Cancel") { onClose() }
                    .buttonStyle(.plain)
                    .font(.system(size: 12))
                    .foregroundColor(.secondary)
                    .padding(.horizontal, 12).padding(.vertical, 7)
                Button {
                    Task { await send() }
                } label: {
                    HStack(spacing: 6) {
                        if sending { ProgressView().controlSize(.small) }
                        Image(systemName: "paperplane.fill").font(.system(size: 11))
                        Text("Send").font(.system(size: 12, weight: .semibold))
                    }
                    .foregroundColor(.white)
                    .padding(.horizontal, 16).padding(.vertical, 7)
                    .background(allRecipients.isEmpty ? Color.zinc800 : Color.matcha600)
                    .cornerRadius(6)
                }
                .buttonStyle(.plain)
                .disabled(allRecipients.isEmpty || sending)
            }
            .padding(.horizontal, 20)
            .padding(.vertical, 14)
        }
        .frame(width: 460, height: 560)
        .background(Color(white: 0.11))
        .onAppear { subject = section.title }
    }

    private func addExtra() {
        let e = extraInput.trimmingCharacters(in: .whitespaces).lowercased()
        guard looksLikeEmail(e), !extraEmails.contains(e) else { return }
        extraEmails.append(e)
        extraInput = ""
    }

    private func send() async {
        guard !allRecipients.isEmpty else { return }
        await MainActor.run { sending = true; resultText = nil }
        let subj = subject.trimmingCharacters(in: .whitespaces)
        let msg = message.trimmingCharacters(in: .whitespacesAndNewlines)
        do {
            let res = try await MatchaWorkService.shared.emailProjectSection(
                projectId: projectId,
                sectionId: section.id,
                recipients: allRecipients,
                subject: subj.isEmpty ? nil : subj,
                message: msg.isEmpty ? nil : msg
            )
            await MainActor.run {
                sending = false
                if res.failed.isEmpty {
                    resultText = "Sent to \(res.sent.count) recipient\(res.sent.count == 1 ? "" : "s")"
                    isError = false
                    Task { try? await Task.sleep(for: .seconds(1)); onClose() }
                } else {
                    isError = !res.ok
                    resultText = "Sent \(res.sent.count), failed \(res.failed.count): \(res.failed.joined(separator: ", "))"
                }
            }
        } catch {
            await MainActor.run {
                sending = false
                isError = true
                resultText = error.localizedDescription
            }
        }
    }
}

/// Wrapping chip row for free-text recipient emails with a remove affordance.
private struct FlowChips: View {
    let items: [String]
    var onRemove: (String) -> Void

    var body: some View {
        // Simple wrapping layout; small N so a LazyVGrid-free flow is fine.
        VStack(alignment: .leading, spacing: 4) {
            ForEach(items, id: \.self) { item in
                HStack(spacing: 4) {
                    Text(item).font(.system(size: 11)).foregroundColor(.white)
                    Button { onRemove(item) } label: {
                        Image(systemName: "xmark.circle.fill").font(.system(size: 10)).foregroundColor(.secondary)
                    }
                    .buttonStyle(.plain)
                }
                .padding(.horizontal, 8).padding(.vertical, 4)
                .background(Color.matcha600.opacity(0.25))
                .cornerRadius(10)
            }
        }
    }
}

// MARK: - Note comments

/// In-app comments on a note. Collaborators can read the thread and post a
/// reply; you can delete your own comments. Flat list (newest at the bottom);
/// the backend keeps a reply_to column for future threading.
struct NoteCommentsView: View {
    let projectId: String
    let section: MWProjectSection
    let currentUserId: String?
    var onClose: () -> Void

    @State private var comments: [MWSectionComment] = []
    @State private var draft: String = ""
    @State private var loading = true
    @State private var sending = false
    @State private var errorText: String? = nil

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                VStack(alignment: .leading, spacing: 1) {
                    Text("Comments").font(.system(size: 15, weight: .semibold)).foregroundColor(.white)
                    Text(section.title.isEmpty ? "Untitled note" : section.title)
                        .font(.system(size: 10)).foregroundColor(.secondary).lineLimit(1)
                }
                Spacer()
                Button { onClose() } label: {
                    Image(systemName: "xmark").font(.system(size: 12, weight: .semibold)).foregroundColor(.secondary)
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, 20).padding(.vertical, 14)

            Divider().opacity(0.2)

            ScrollView {
                if loading {
                    ProgressView().controlSize(.small).padding(.vertical, 40)
                } else if comments.isEmpty {
                    Text("No comments yet. Start the discussion.")
                        .font(.system(size: 12)).foregroundColor(.secondary)
                        .frame(maxWidth: .infinity).padding(.vertical, 40)
                } else {
                    VStack(alignment: .leading, spacing: 14) {
                        ForEach(comments) { c in commentRow(c) }
                    }
                    .padding(16)
                }
            }

            if let errorText {
                Text(errorText)
                    .font(.system(size: 10)).foregroundColor(.red)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal, 16).padding(.bottom, 4)
            }

            Divider().opacity(0.2)

            HStack(alignment: .bottom, spacing: 8) {
                TextField("Write a comment…", text: $draft, axis: .vertical)
                    .textFieldStyle(.plain)
                    .font(.system(size: 12))
                    .foregroundColor(.white)
                    .lineLimit(1...5)
                    .padding(.horizontal, 10).padding(.vertical, 8)
                    .background(Color.zinc800).cornerRadius(8)
                Button {
                    Task { await send() }
                } label: {
                    if sending {
                        ProgressView().controlSize(.small)
                    } else {
                        Image(systemName: "paperplane.fill").font(.system(size: 13))
                            .foregroundColor(canSend ? .matcha500 : .secondary)
                    }
                }
                .buttonStyle(.plain)
                .disabled(!canSend || sending)
            }
            .padding(.horizontal, 16).padding(.vertical, 12)
        }
        .frame(width: 440, height: 560)
        .background(Color(white: 0.11))
        .task { await load() }
    }

    private var canSend: Bool {
        !draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    @ViewBuilder
    private func commentRow(_ c: MWSectionComment) -> some View {
        HStack(alignment: .top, spacing: 10) {
            ChannelAvatarView(senderId: c.userId, payloadURL: c.avatarUrl, name: c.authorName ?? "?", size: 28)
            VStack(alignment: .leading, spacing: 3) {
                HStack(spacing: 6) {
                    Text(c.authorName ?? "Someone")
                        .font(.system(size: 12, weight: .semibold)).foregroundColor(.white)
                    if let ts = c.createdAt, let d = parseMWDate(ts) {
                        Text(relativeShort(d)).font(.system(size: 9)).foregroundColor(.secondary)
                    }
                    Spacer()
                    if c.userId == currentUserId {
                        Button { Task { await delete(c) } } label: {
                            Image(systemName: "trash").font(.system(size: 9)).foregroundColor(.red.opacity(0.7))
                        }
                        .buttonStyle(.plain)
                        .help("Delete comment")
                    }
                }
                Text(c.content)
                    .font(.system(size: 12)).foregroundColor(.white.opacity(0.9))
                    .fixedSize(horizontal: false, vertical: true)
                    .textSelection(.enabled)
            }
        }
    }

    private func relativeShort(_ date: Date) -> String {
        let secs = Int(Date().timeIntervalSince(date))
        if secs < 60 { return "just now" }
        if secs < 3600 { return "\(secs/60)m" }
        if secs < 86400 { return "\(secs/3600)h" }
        return "\(secs/86400)d"
    }

    private func load() async {
        await MainActor.run { loading = true; errorText = nil }
        do {
            let list = try await MatchaWorkService.shared.listSectionComments(projectId: projectId, sectionId: section.id)
            await MainActor.run { comments = list; loading = false }
        } catch {
            await MainActor.run { errorText = error.localizedDescription; loading = false }
        }
    }

    private func send() async {
        let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        await MainActor.run { sending = true; errorText = nil }
        do {
            let created = try await MatchaWorkService.shared.addSectionComment(
                projectId: projectId, sectionId: section.id, content: text
            )
            await MainActor.run {
                comments.append(created)
                draft = ""
                sending = false
            }
        } catch {
            await MainActor.run { errorText = error.localizedDescription; sending = false }
        }
    }

    private func delete(_ c: MWSectionComment) async {
        do {
            try await MatchaWorkService.shared.deleteSectionComment(projectId: projectId, sectionId: section.id, commentId: c.id)
            await MainActor.run { comments.removeAll { $0.id == c.id } }
        } catch {
            await MainActor.run { errorText = error.localizedDescription }
        }
    }
}
