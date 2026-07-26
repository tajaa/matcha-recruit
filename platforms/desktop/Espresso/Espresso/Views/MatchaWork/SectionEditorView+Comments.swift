import SwiftUI

// MARK: - Anchored highlight-to-comment threads
//
// Split out of SectionEditorView.swift: the comment API calls, the derived
// highlight marks, and the three floating cards layered over the editor.

extension SectionEditorView {

    // MARK: - Derived

    /// Unresolved, anchored comments → in-text yellow highlights.
    var commentHighlights: [CommentHighlightMark] {
        comments.compactMap { c in
            guard !c.isResolved, let a = c.anchorStart, let b = c.anchorEnd, b > a else { return nil }
            return CommentHighlightMark(id: c.id, anchor: a, head: b)
        }
    }

    var unresolvedCount: Int { comments.filter { !$0.isResolved }.count }

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

    // MARK: - Selection / thread state

    func selectionChanged(_ rect: CGRect?, _ a: Int, _ b: Int) {
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

    /// A highlight was clicked — open its thread anchored at `rect`. Both the
    /// editable and watcher editors route their `onCommentTap` here; the body
    /// used to inline the same four assignments twice.
    func openCommentThread(_ id: String, at rect: CGRect) {
        openThreadId = id
        threadRect = rect
        selRect = nil
        composing = false
    }

    /// Wipe every piece of comment UI. Called when the editor switches notes.
    func resetCommentUI() {
        selRect = nil; selRange = nil; composing = false
        openThreadId = nil; threadRect = nil; showAllComments = false
    }

    /// Select + scroll to a comment's anchored range in whichever editor is live.
    func jumpTo(_ c: MWSectionComment) {
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

    // MARK: - API

    func loadComments() async {
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
        post(body, replyTo: rootId)
    }

    func postGeneralComment(_ body: String) {
        post(body, replyTo: nil)
    }

    /// General comment / reply — the same call but for `replyToCommentId`.
    private func post(_ body: String, replyTo rootId: String?) {
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

    func setResolved(_ c: MWSectionComment, _ val: Bool) {
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

    func deleteComment(_ c: MWSectionComment) {
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

    // MARK: - Top-bar entry point

    /// "Comments (N)" in the editor's top bar → the all-comments popover.
    var allCommentsButton: some View {
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
    }

    // MARK: - Floating cards over the editor

    private func clampX(_ x: CGFloat, width: CGFloat, card: CGFloat) -> CGFloat {
        max(0, min(x, max(0, width - card)))
    }

    /// Floating comment UI layered over the editor: an "add comment" bubble on a
    /// fresh selection, the inline compose card, and the clicked-highlight thread.
    @ViewBuilder
    func commentAffordances(width: CGFloat) -> some View {
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
