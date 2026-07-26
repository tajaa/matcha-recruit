import SwiftUI

/// One message in the channel timeline: avatar + sender + time, optional reply
/// quote, content, image/file attachments, reaction pills, and pending/failed
/// affordances. Context menu drives reply / react / edit / delete.
struct MessageRow: View {
    let message: ChannelMessage
    let currentUserId: String
    var onReply: (ChannelMessage) -> Void
    var onToggleReaction: (ChannelMessage, String) -> Void
    var onEdit: (ChannelMessage) -> Void
    var onDelete: (ChannelMessage) -> Void
    var onRetry: (ChannelMessage) -> Void

    private static let quickReactions = ["👍", "❤️", "😂", "🎉", "👀", "✅"]
    private var isMine: Bool { message.senderId == currentUserId }
    private var isDeleted: Bool { message.deletedAt != nil }

    var body: some View {
        if isDeleted {
            deletedRow
        } else {
            content
                .contextMenu { menu }
        }
    }

    private var deletedRow: some View {
        HStack {
            Image(systemName: "trash").font(.caption2)
            Text("Message deleted").font(.caption).italic()
        }
        .foregroundStyle(.tertiary)
        .padding(.leading, 48)
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.vertical, 2)
    }

    private var content: some View {
        HStack(alignment: .top, spacing: 8) {
            Avatar(url: message.senderAvatarUrl, name: message.senderName, size: 36)
            VStack(alignment: .leading, spacing: 3) {
                HStack(spacing: 6) {
                    Text(message.senderName).font(.subheadline.bold())
                    Text(ChatTime.clock(message.createdAt))
                        .font(.caption2).foregroundStyle(.secondary)
                    if message.editedAt != nil {
                        Text("(edited)").font(.caption2).foregroundStyle(.tertiary)
                    }
                }
                if let reply = message.replyPreview {
                    replyQuote(reply)
                }
                if !displayText.isEmpty {
                    Text(displayText)
                        .font(.body)
                        .textSelection(.enabled)
                }
                if !message.attachments.isEmpty {
                    attachments
                }
                if !message.reactions.isEmpty {
                    reactionPills
                }
                if message.failed {
                    Button { onRetry(message) } label: {
                        Label("Failed to send · tap to retry", systemImage: "exclamationmark.circle")
                            .font(.caption2).foregroundStyle(.red)
                    }
                }
            }
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 4)
        .opacity(message.pending ? 0.55 : 1)
    }

    private func replyQuote(_ reply: ReplyPreview) -> some View {
        HStack(spacing: 6) {
            Rectangle().fill(.tint.opacity(0.6)).frame(width: 2).clipShape(Capsule())
            VStack(alignment: .leading, spacing: 0) {
                Text(reply.senderName).font(.caption2.bold()).foregroundStyle(.secondary)
                Text(reply.content.isEmpty ? "Attachment" : reply.content)
                    .font(.caption2).foregroundStyle(.secondary).lineLimit(1)
            }
        }
        .padding(.vertical, 1)
    }

    @ViewBuilder
    private var attachments: some View {
        VStack(alignment: .leading, spacing: 6) {
            ForEach(message.attachments, id: \.url) { att in
                if att.contentType.hasPrefix("image/"), let u = URL(string: att.url) {
                    Button { SafeURL.open(att.url) } label: {
                        AsyncImage(url: u) { phase in
                            if let image = phase.image {
                                image.resizable().scaledToFill()
                            } else {
                                RoundedRectangle(cornerRadius: 10)
                                    .fill(Color(.secondarySystemBackground))
                                    .overlay(ProgressView())
                            }
                        }
                        .frame(maxWidth: 220, maxHeight: 220)
                        .clipShape(RoundedRectangle(cornerRadius: 10))
                    }
                    .buttonStyle(.plain)
                } else {
                    Button { SafeURL.open(att.url) } label: {
                        Label(att.filename, systemImage: "doc.fill")
                            .font(.caption)
                            .padding(.horizontal, 10).padding(.vertical, 6)
                            .background(Color(.secondarySystemBackground), in: Capsule())
                    }
                    .buttonStyle(.plain)
                }
            }
        }
    }

    private var reactionPills: some View {
        FlowRow(spacing: 4) {
            ForEach(message.reactions, id: \.emoji) { r in
                let mine = r.userIds.contains(currentUserId)
                Button { onToggleReaction(message, r.emoji) } label: {
                    HStack(spacing: 3) {
                        Text(r.emoji).font(.caption)
                        Text("\(r.count)").font(.caption2).foregroundStyle(mine ? .white : .secondary)
                    }
                    .padding(.horizontal, 8).padding(.vertical, 3)
                    .background(mine ? AnyShapeStyle(.tint) : AnyShapeStyle(Color(.secondarySystemBackground)),
                                in: Capsule())
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.top, 2)
    }

    @ViewBuilder
    private var menu: some View {
        ControlGroup {
            ForEach(Self.quickReactions, id: \.self) { emoji in
                Button(emoji) { onToggleReaction(message, emoji) }
            }
        }
        Button { onReply(message) } label: { Label("Reply", systemImage: "arrowshape.turn.up.left") }
        if !displayText.isEmpty {
            Button {
                UIPasteboard.general.string = displayText
            } label: { Label("Copy", systemImage: "doc.on.doc") }
        }
        if isMine {
            Button { onEdit(message) } label: { Label("Edit", systemImage: "pencil") }
            Button(role: .destructive) { onDelete(message) } label: { Label("Delete", systemImage: "trash") }
        }
    }

    /// Strip the machine-readable kanban-ticket marker the macOS client may
    /// embed (`⟦ticket:id|title|col⟧`) — iOS chat has no board to link to.
    private var displayText: String {
        guard message.content.contains("⟦ticket:") else { return message.content }
        return message.content
            .replacingOccurrences(of: #"⟦ticket:[^⟧]*⟧\n?"#, with: "", options: .regularExpression)
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }
}

/// Minimal wrapping HStack for reaction pills (iOS 16+ Layout).
struct FlowRow: Layout {
    var spacing: CGFloat = 4

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let maxWidth = proposal.width ?? .infinity
        var x: CGFloat = 0, y: CGFloat = 0, rowHeight: CGFloat = 0
        for sub in subviews {
            let size = sub.sizeThatFits(.unspecified)
            if x + size.width > maxWidth, x > 0 {
                x = 0; y += rowHeight + spacing; rowHeight = 0
            }
            x += size.width + spacing
            rowHeight = max(rowHeight, size.height)
        }
        return CGSize(width: maxWidth == .infinity ? x : maxWidth, height: y + rowHeight)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let maxWidth = bounds.width
        var x: CGFloat = bounds.minX, y: CGFloat = bounds.minY, rowHeight: CGFloat = 0
        for sub in subviews {
            let size = sub.sizeThatFits(.unspecified)
            if x + size.width > bounds.minX + maxWidth, x > bounds.minX {
                x = bounds.minX; y += rowHeight + spacing; rowHeight = 0
            }
            sub.place(at: CGPoint(x: x, y: y), proposal: ProposedViewSize(size))
            x += size.width + spacing
            rowHeight = max(rowHeight, size.height)
        }
    }
}
