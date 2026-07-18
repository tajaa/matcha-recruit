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

    // MARK: Comments (anchored highlight-to-comment + general)
    @State private var comments: [MWSectionComment] = []
    /// Live selection rect (editor-local) + char range, for the "add comment"
    /// affordance. Set from MarkdownTextEditor.onSelectionRectChange.
    @State private var selRect: CGRect? = nil
    @State private var selRange: (Int, Int)? = nil
    @State private var composing = false
    @State private var composeText = ""
    /// The compose card overlays the NSTextView editor; without explicitly
    /// driving first responder, the TextField never grabs the keyboard and
    /// typed text never lands (button stays disabled). Focus it when the card
    /// opens.
    @FocusState private var composeFocused: Bool
    /// An opened thread (clicked highlight) + the rect to anchor its popover.
    @State private var openThreadId: String? = nil
    @State private var threadRect: CGRect? = nil
    @State private var showAllComments = false

    /// Unresolved, anchored comments → in-text yellow highlights.
    private var commentHighlights: [CommentHighlightMark] {
        comments.compactMap { c in
            guard !c.isResolved, let a = c.anchorStart, let b = c.anchorEnd, b > a else { return nil }
            return CommentHighlightMark(id: c.id, anchor: a, head: b)
        }
    }

    /// A thread = the root comment + its replies, oldest first.
    private func thread(for rootId: String) -> [MWSectionComment] {
        guard let root = comments.first(where: { $0.id == rootId }) else { return [] }
        let replies: [MWSectionComment] = comments.filter { $0.replyToCommentId == rootId }
        let sortedReplies = replies.sorted { ($0.createdAt ?? "") < ($1.createdAt ?? "") }
        var result: [MWSectionComment] = [root]
        result.append(contentsOf: sortedReplies)
        return result
    }

    private func quote(_ a: Int, _ b: Int) -> String {
        let ns = content as NSString
        let lo = max(0, min(a, ns.length))
        let hi = max(lo, min(b, ns.length))
        return ns.substring(with: NSRange(location: lo, length: hi - lo))
    }

    private func loadComments() async {
        guard let pid = projectId else { return }
        if let list = try? await MatchaWorkService.shared.listSectionComments(projectId: pid, sectionId: section.id) {
            await MainActor.run { comments = list }
        }
    }

    private func postAnchoredComment() {
        guard let pid = projectId, let (a, b) = selRange else { return }
        let body = composeText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !body.isEmpty else { return }
        let q = quote(a, b)
        Task {
            if let c = try? await MatchaWorkService.shared.addSectionComment(
                projectId: pid, sectionId: section.id, content: body,
                anchorStart: a, anchorEnd: b, quotedText: q
            ) {
                await MainActor.run {
                    comments.append(c)
                    composeText = ""; composing = false; composeFocused = false
                    selRect = nil; selRange = nil
                }
            }
        }
    }

    private func postReply(to rootId: String, _ body: String) {
        guard let pid = projectId else { return }
        let text = body.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        Task {
            if let c = try? await MatchaWorkService.shared.addSectionComment(
                projectId: pid, sectionId: section.id, content: text, replyToCommentId: rootId
            ) {
                await MainActor.run { comments.append(c) }
            }
        }
    }

    private func postGeneralComment(_ body: String) {
        guard let pid = projectId else { return }
        let text = body.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        Task {
            if let c = try? await MatchaWorkService.shared.addSectionComment(
                projectId: pid, sectionId: section.id, content: text
            ) {
                await MainActor.run { comments.append(c) }
            }
        }
    }

    private func setResolved(_ c: MWSectionComment, _ val: Bool) {
        guard let pid = projectId else { return }
        Task {
            if let u = try? await MatchaWorkService.shared.resolveSectionComment(
                projectId: pid, sectionId: section.id, commentId: c.id, resolved: val
            ) {
                await MainActor.run {
                    if let i = comments.firstIndex(where: { $0.id == u.id }) { comments[i] = u }
                    if val, openThreadId == c.id { openThreadId = nil }
                }
            }
        }
    }

    private func deleteComment(_ c: MWSectionComment) {
        guard let pid = projectId else { return }
        Task {
            try? await MatchaWorkService.shared.deleteSectionComment(
                projectId: pid, sectionId: section.id, commentId: c.id
            )
            await MainActor.run {
                comments.removeAll { $0.id == c.id || $0.replyToCommentId == c.id }
                if openThreadId == c.id { openThreadId = nil }
            }
        }
    }

    private func selectionChanged(_ rect: CGRect?, _ a: Int, _ b: Int) {
        // While the compose card is open, freeze the captured selection — the
        // editor resigning first responder to the comment field can emit a stray
        // selection event that would otherwise clear selRange (nothing to anchor)
        // or flip `composing` off and dismiss the card mid-type.
        if composing { return }
        if let rect, b > a {
            selRect = rect; selRange = (a, b)
            openThreadId = nil
        } else {
            selRect = nil; selRange = nil
        }
    }

    private var unresolvedCount: Int { comments.filter { !$0.isResolved }.count }

    /// Select + scroll to a comment's anchored range in whichever editor is live.
    private func jumpTo(_ c: MWSectionComment) {
        showAllComments = false
        guard let a = c.anchorStart, let b = c.anchorEnd, b > a else { return }
        guard let tv = (lockedByName == nil ? controller : watcherController).textView else { return }
        let len = (tv.string as NSString).length
        let lo = max(0, min(a, len)); let hi = max(lo, min(b, len))
        let r = NSRange(location: lo, length: hi - lo)
        tv.setSelectedRange(r)
        tv.scrollRangeToVisible(r)
        tv.window?.makeFirstResponder(tv)
    }

    private func clampX(_ x: CGFloat, width: CGFloat, card: CGFloat) -> CGFloat {
        max(0, min(x, max(0, width - card)))
    }

    /// Floating comment UI layered over the editor: an "add comment" bubble on a
    /// fresh selection, the inline compose card, and the clicked-highlight thread.
    @ViewBuilder
    private func commentAffordances(width: CGFloat) -> some View {
        if !composing, let rect = selRect, selRange != nil {
            addCommentBubble
                .offset(x: clampX(rect.minX, width: width, card: 120), y: rect.maxY + 4)
        }
        if composing, let rect = selRect {
            composeCard
                .offset(x: clampX(rect.minX, width: width, card: 260), y: rect.maxY + 4)
        }
        if let id = openThreadId, let rect = threadRect {
            threadCard(id)
                .offset(x: clampX(rect.minX, width: width, card: 280), y: rect.maxY + 4)
        }
    }

    private var addCommentBubble: some View {
        Button {
            composeText = ""
            composing = true
        } label: {
            HStack(spacing: 4) {
                Image(systemName: "text.bubble.fill").font(.system(size: 10))
                Text("Comment").font(.system(size: 11, weight: .semibold))
            }
            .padding(.horizontal, 9).padding(.vertical, 5)
            .foregroundColor(.white)
            .background(Color.matcha600)
            .cornerRadius(6)
            .shadow(radius: 4)
        }
        .buttonStyle(.plain)
    }

    private var composeCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            if let (a, b) = selRange {
                Text("\u{201C}\(String(quote(a, b).prefix(80)))\u{201D}")
                    .font(.system(size: 10)).italic()
                    .foregroundColor(.secondary).lineLimit(2)
            }
            TextField("Add a comment…", text: $composeText, axis: .vertical)
                .textFieldStyle(.plain).font(.system(size: 12))
                // Tinted distinct from the (white) document text so the comment
                // reads as a comment, not part of the note.
                .foregroundColor(.matcha500)
                .tint(.matcha500)
                .focused($composeFocused)
                .lineLimit(1...4)
                .padding(8).background(Color.zinc800).cornerRadius(6)
            HStack {
                Spacer()
                Button("Cancel") { composing = false; composeFocused = false; selRect = nil; selRange = nil }
                    .buttonStyle(.plain).font(.system(size: 11)).foregroundColor(.secondary)
                let empty = composeText.trimmingCharacters(in: .whitespaces).isEmpty
                Button("Comment") { postAnchoredComment() }
                    .buttonStyle(.plain).font(.system(size: 11, weight: .semibold))
                    .foregroundColor(.white).padding(.horizontal, 10).padding(.vertical, 4)
                    .background(empty ? Color.zinc800 : Color.matcha600)
                    .cornerRadius(5)
                    .disabled(empty)
            }
        }
        .padding(10).frame(width: 260)
        .background(Color(white: 0.14)).cornerRadius(8)
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(Color.white.opacity(0.1), lineWidth: 1))
        .shadow(radius: 8)
        // Grab the keyboard the moment the card mounts (next runloop tick so the
        // field is in the hierarchy and AppKit hands over first responder).
        .onAppear { DispatchQueue.main.async { composeFocused = true } }
    }

    @ViewBuilder
    private func threadCard(_ id: String) -> some View {
        let items = thread(for: id)
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("Comment").font(.system(size: 11, weight: .semibold)).foregroundColor(.matcha500)
                Spacer()
                if let root = items.first {
                    Button { setResolved(root, true) } label: {
                        Label("Resolve", systemImage: "checkmark").font(.system(size: 10))
                    }
                    .buttonStyle(.plain).foregroundColor(.secondary)
                    .help("Resolve — hides the highlight")
                }
                Button { openThreadId = nil } label: {
                    Image(systemName: "xmark").font(.system(size: 10))
                }
                .buttonStyle(.plain).foregroundColor(.secondary)
            }
            if let root = items.first, root.isAnchored, let q = root.quotedText, !q.isEmpty {
                Text("\u{201C}\(String(q.prefix(80)))\u{201D}")
                    .font(.system(size: 10)).italic().foregroundColor(.secondary).lineLimit(2)
            }
            ForEach(items) { c in
                VStack(alignment: .leading, spacing: 2) {
                    HStack(spacing: 6) {
                        Text(c.authorName ?? "Someone").font(.system(size: 11, weight: .semibold)).foregroundColor(.white)
                        Spacer()
                        if c.userId == currentUserId {
                            Button { deleteComment(c) } label: {
                                Image(systemName: "trash").font(.system(size: 9)).foregroundColor(.red.opacity(0.7))
                            }
                            .buttonStyle(.plain)
                        }
                    }
                    Text(c.content).font(.system(size: 12)).foregroundColor(.white.opacity(0.9))
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            ThreadReplyField { postReply(to: id, $0) }
        }
        .padding(10).frame(width: 280)
        .background(Color(white: 0.14)).cornerRadius(8)
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(Color.white.opacity(0.1), lineWidth: 1))
        .shadow(radius: 8)
    }

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
                Button {
                    showAllComments.toggle()
                } label: {
                    HStack(spacing: 4) {
                        Image(systemName: "bubble.left.and.bubble.right").font(.system(size: 11))
                        Text(unresolvedCount > 0 ? "Comments (\(unresolvedCount))" : "Comments")
                            .font(.system(size: 12, weight: .medium))
                    }
                    .foregroundColor(unresolvedCount > 0 ? .matcha500 : .white.opacity(0.85))
                }
                .buttonStyle(.plain)
                .help("All comments on this note")
                .popover(isPresented: $showAllComments, arrowEdge: .bottom) {
                    NoteCommentsView(
                        comments: comments,
                        currentUserId: currentUserId,
                        onAdd: { postGeneralComment($0) },
                        onResolve: { setResolved($0, $1) },
                        onDelete: { deleteComment($0) },
                        onJump: { jumpTo($0) },
                        onClose: { showAllComments = false }
                    )
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
                            onCommentTap: { id, rect in openThreadId = id; threadRect = rect; selRect = nil; composing = false },
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

                // Content editor
                GeometryReader { geo in
                    ZStack(alignment: .topLeading) {
                        MarkdownTextEditor(
                            text: $content,
                            controller: $controller,
                            onSelectionChange: { anchor, head in
                                onCaretMove?(anchor, head)
                            },
                            commentHighlights: commentHighlights,
                            onCommentTap: { id, rect in openThreadId = id; threadRect = rect; selRect = nil; composing = false },
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
            // Reset comment UI for the new note.
            selRect = nil; selRange = nil; composing = false
            openThreadId = nil; threadRect = nil; showAllComments = false
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

/// Small reply field for the inline thread popover (own state so typing doesn't
/// disturb the editor).
private struct ThreadReplyField: View {
    var onSend: (String) -> Void
    @State private var text = ""

    var body: some View {
        HStack(spacing: 6) {
            TextField("Reply…", text: $text, axis: .vertical)
                .textFieldStyle(.plain).font(.system(size: 11)).foregroundColor(.white)
                .lineLimit(1...3)
                .padding(6).background(Color.zinc800).cornerRadius(5)
            let empty = text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            Button { onSend(text); text = "" } label: {
                Image(systemName: "paperplane.fill").font(.system(size: 11))
                    .foregroundColor(empty ? .secondary : .matcha500)
            }
            .buttonStyle(.plain).disabled(empty)
        }
    }
}
