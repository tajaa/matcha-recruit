import SwiftUI

// MARK: - Note comments panel

/// Driven (no self-load) browse-all-comments panel, shown as a popover from the
/// note's "Comments" button. Lists top-level comments (anchored + general),
/// shows each anchored comment's quote (tap to jump to it in the text), and
/// supports resolve / reopen / delete + a general (whole-note) composer. The
/// per-highlight reply thread lives inline in the editor, not here.
struct NoteCommentsView: View {
    let comments: [MWSectionComment]
    let currentUserId: String?
    var onAdd: (String) -> Void
    var onResolve: (MWSectionComment, Bool) -> Void
    var onDelete: (MWSectionComment) -> Void
    var onJump: (MWSectionComment) -> Void
    var onClose: () -> Void

    @State private var draft = ""
    @State private var showResolved = false

    private var roots: [MWSectionComment] {
        comments.filter { $0.replyToCommentId == nil }
    }
    private var visible: [MWSectionComment] {
        showResolved ? roots : roots.filter { !$0.isResolved }
    }
    private var resolvedCount: Int { roots.filter { $0.isResolved }.count }

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text("Comments").font(.system(size: 14, weight: .semibold)).foregroundColor(.white)
                Spacer()
                if resolvedCount > 0 {
                    Button { showResolved.toggle() } label: {
                        Text(showResolved ? "Hide resolved" : "Show resolved (\(resolvedCount))")
                            .font(.system(size: 10)).foregroundColor(.secondary)
                    }
                    .buttonStyle(.plain)
                }
                Button { onClose() } label: {
                    Image(systemName: "xmark").font(.system(size: 11, weight: .semibold)).foregroundColor(.secondary)
                }
                .buttonStyle(.plain)
            }
            .padding(.horizontal, 14).padding(.vertical, 10)

            Divider().opacity(0.2)

            ScrollView {
                if visible.isEmpty {
                    Text("No comments yet.\nHighlight text in the note to comment on it.")
                        .font(.system(size: 11)).foregroundColor(.secondary)
                        .multilineTextAlignment(.center)
                        .frame(maxWidth: .infinity).padding(.vertical, 36).padding(.horizontal, 16)
                } else {
                    VStack(alignment: .leading, spacing: 12) {
                        ForEach(visible) { c in commentRow(c) }
                    }
                    .padding(14)
                }
            }

            Divider().opacity(0.2)

            HStack(alignment: .bottom, spacing: 8) {
                TextField("Comment on the whole note…", text: $draft, axis: .vertical)
                    .textFieldStyle(.plain).font(.system(size: 12)).foregroundColor(.white)
                    .lineLimit(1...4)
                    .padding(.horizontal, 10).padding(.vertical, 8)
                    .background(Color.zinc800).cornerRadius(8)
                let empty = draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                Button {
                    onAdd(draft); draft = ""
                } label: {
                    Image(systemName: "paperplane.fill").font(.system(size: 13))
                        .foregroundColor(empty ? .secondary : .matcha500)
                }
                .buttonStyle(.plain).disabled(empty)
            }
            .padding(.horizontal, 12).padding(.vertical, 10)
        }
        .frame(width: 360, height: 460)
        .background(Color(white: 0.11))
    }

    @ViewBuilder
    private func commentRow(_ c: MWSectionComment) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(alignment: .top, spacing: 8) {
                ChannelAvatarView(senderId: c.userId, payloadURL: c.avatarUrl, name: c.authorName ?? "?", size: 22)
                VStack(alignment: .leading, spacing: 3) {
                    HStack(spacing: 6) {
                        Text(c.authorName ?? "Someone")
                            .font(.system(size: 11, weight: .semibold)).foregroundColor(.white)
                        if let ts = c.createdAt, let d = parseMWDate(ts) {
                            Text(relativeShort(d)).font(.system(size: 9)).foregroundColor(.secondary)
                        }
                        if c.isResolved {
                            Text("RESOLVED").font(.system(size: 7, weight: .bold)).tracking(0.4)
                                .foregroundColor(.matcha500)
                                .padding(.horizontal, 4).padding(.vertical, 1)
                                .background(Color.matcha500.opacity(0.15)).cornerRadius(3)
                        }
                        Spacer()
                    }
                    if c.isAnchored, let q = c.quotedText, !q.isEmpty {
                        Button { onJump(c) } label: {
                            Text("“\(String(q.prefix(80)))”")
                                .font(.system(size: 10)).italic()
                                .foregroundColor(.matcha500).lineLimit(2)
                                .multilineTextAlignment(.leading)
                        }
                        .buttonStyle(.plain).help("Jump to this highlight")
                    }
                    Text(c.content)
                        .font(.system(size: 12)).foregroundColor(.white.opacity(0.9))
                        .fixedSize(horizontal: false, vertical: true).textSelection(.enabled)
                }
            }
            HStack(spacing: 12) {
                Spacer()
                Button { onResolve(c, !c.isResolved) } label: {
                    Text(c.isResolved ? "Reopen" : "Resolve")
                        .font(.system(size: 10, weight: .medium)).foregroundColor(.secondary)
                }
                .buttonStyle(.plain)
                if c.userId == currentUserId {
                    Button { onDelete(c) } label: {
                        Image(systemName: "trash").font(.system(size: 9)).foregroundColor(.red.opacity(0.7))
                    }
                    .buttonStyle(.plain).help("Delete comment")
                }
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
}
