import SwiftUI
import AppKit

struct ChannelMessageRowView: View {
    @Environment(AppState.self) private var appState
    let msg: ChannelMessage
    let members: [ChannelMember]
    let currentUserId: String
    let isAdmin: Bool
    @Binding var hoveredMessageId: String?
    let onReply: (ChannelMessage) -> Void
    let onToggleReaction: (String, String) -> Void
    let onRequestDelete: (ChannelMessage) -> Void
    let onRequestEdit: (ChannelMessage) -> Void
    /// Open an attachment in the shared preview. Hoisted to the parent
    /// (ChannelDetailView) so the preview sheet survives row re-renders /
    /// LazyVStack recycling — a per-row `.sheet` dropped the binding when a
    /// new message streamed in, which is why media open was flaky.
    let onOpenAttachment: (ChannelAttachment) -> Void

    var body: some View {
        // iMessage-style sides: my messages render right in an accent bubble
        // (no avatar/name); everyone else renders left in a card bubble with
        // avatar + name. See [[werk-theme-conventions]] sent/received rule.
        let isMine = msg.senderId == currentUserId
        return VStack(alignment: isMine ? .trailing : .leading, spacing: 2) {
            if msg.replyPreview != nil {
                replyPreviewView(isMine: isMine)
            }

            HStack(alignment: .top, spacing: 8) {
                if isMine {
                    Spacer(minLength: 44)
                } else {
                    senderAvatar(msg)
                        .frame(width: 36, height: 36)
                }

                VStack(alignment: isMine ? .trailing : .leading, spacing: 3) {
                    HStack(spacing: 6) {
                        if !isMine {
                            Text(msg.senderName)
                                .font(.system(size: 13, weight: .semibold))
                                .foregroundColor(appState.themeText)
                        }
                        Text(formatTimestamp(msg.createdAt))
                            .font(.system(size: 10))
                            .foregroundColor(appState.themeTextSecondary)
                        if msg.editedAt != nil && msg.deletedAt == nil {
                            Text("· edited")
                                .font(.system(size: 10))
                                .foregroundColor(appState.themeTextSecondary)
                        }
                        if msg.failed {
                            HStack(spacing: 3) {
                                Image(systemName: "exclamationmark.circle.fill")
                                    .font(.system(size: 10))
                                    .foregroundColor(.red)
                                Text("not sent")
                                    .font(.system(size: 10, weight: .medium))
                                    .foregroundColor(.red)
                            }
                        } else if msg.pending {
                            Text("sending…")
                                .font(.system(size: 10))
                                .foregroundColor(appState.themeText.opacity(0.4))
                        }
                    }

                    if msg.deletedAt != nil {
                        Text("message deleted")
                            .font(.system(size: 12))
                            .foregroundColor(appState.themeTextSecondary)
                            .italic()
                    } else {
                        if !msg.content.isEmpty {
                            Text(mentionAttributedContent(msg))
                                .font(.system(size: 13))
                                .foregroundColor(isMine ? appState.themeOnAccent : appState.themeText)
                                .textSelection(.enabled)
                                .multilineTextAlignment(.leading)
                                .fixedSize(horizontal: false, vertical: true)
                                .padding(.horizontal, 10)
                                .padding(.vertical, 7)
                                .background(
                                    RoundedRectangle(cornerRadius: 14, style: .continuous)
                                        .fill(isMine ? appState.themeAccent : appState.themeCard)
                                )
                        }
                        if !msg.attachments.isEmpty {
                            attachmentList(msg.attachments, isMine: isMine)
                        }
                    }

                    if !msg.reactions.isEmpty {
                        reactionPills
                    }
                }

                if isMine {
                    senderAvatar(msg)
                        .frame(width: 36, height: 36)
                } else {
                    Spacer(minLength: 44)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: isMine ? .trailing : .leading)
        .padding(.vertical, 4)
        .padding(.horizontal, 4)
        .background(
            RoundedRectangle(cornerRadius: 6)
                .fill(hoveredMessageId == msg.id ? appState.themeText.opacity(0.04) : Color.clear)
        )
        .onHover { hovering in hoveredMessageId = hovering ? msg.id : nil }
        .overlay(alignment: isMine ? .topLeading : .topTrailing) {
            // Hide hover actions (reply, react) on pending/failed rows — they'd
            // route a request keyed by the client UUID and 404 server-side.
            // Sits on the bubble's inner edge (leading for own messages).
            if hoveredMessageId == msg.id && msg.deletedAt == nil
                && !msg.pending && !msg.failed {
                hoverActions
            }
        }
        .contentShape(Rectangle())
        .contextMenu {
            Button {
                NSPasteboard.general.clearContents()
                NSPasteboard.general.setString(msg.content, forType: .string)
            } label: {
                Label("Copy text", systemImage: "doc.on.doc")
            }
            .disabled(msg.content.isEmpty)

            Button { onReply(msg) } label: {
                Label("Reply", systemImage: "arrowshape.turn.up.left")
            }

            // Author can edit their own text message within the 15-min window.
            // Attachment-only messages (no text bubble) aren't editable — delete instead.
            let canEdit = msg.senderId == currentUserId && msg.deletedAt == nil
                && !msg.pending && !msg.failed && !msg.content.isEmpty && withinEditWindow
            if canEdit {
                Button { onRequestEdit(msg) } label: {
                    Label("Edit", systemImage: "pencil")
                }
            }

            Divider()

            Menu {
                ForEach(["👍", "❤️", "🎉", "😂", "🤔", "👀"], id: \.self) { emoji in
                    Button(emoji) {
                        onToggleReaction(msg.id, emoji)
                    }
                }
            } label: {
                Label("React", systemImage: "face.smiling")
            }

            // Author can delete their own; channel owner / moderator (or
            // global admin) can delete anyone's. `isAdmin` already covers
            // those three roles. `deletedAt` gates redundant delete on
            // already-tombstoned messages. Pending/failed rows have no
            // server-side row to delete (msg.id is the client UUID until
            // the echo reconciles), so the DELETE would 404.
            // Admins/mods delete anyone's anytime; authors only within the window.
            let canDelete = (isAdmin || (msg.senderId == currentUserId && withinEditWindow))
                && msg.deletedAt == nil
                && !msg.pending
                && !msg.failed
            if canDelete {
                Divider()
                Button(role: .destructive) {
                    onRequestDelete(msg)
                } label: {
                    Label("Delete message", systemImage: "trash")
                }
            }
        }
    }

    /// Reply preview — the original message this one replies to, padded to the
    /// sender's side (trailing for own messages).
    @ViewBuilder
    private func replyPreviewView(isMine: Bool) -> some View {
        if let rp = msg.replyPreview {
            HStack(alignment: .top, spacing: 6) {
                RoundedRectangle(cornerRadius: 1)
                    .fill(appState.themeAccent.opacity(0.5))
                    .frame(width: 2)
                VStack(alignment: .leading, spacing: 3) {
                    Text(rp.senderName)
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundColor(appState.themeAccent)
                    if !rp.content.isEmpty {
                        Text(rp.content)
                            .font(.system(size: 10))
                            .foregroundColor(appState.themeText.opacity(0.5))
                            .lineLimit(2)
                    }
                    if !rp.attachments.isEmpty {
                        HStack(spacing: 4) {
                            ForEach(rp.attachments.prefix(3), id: \.self) { att in
                                if att.contentType.hasPrefix("image/"), let url = URL(string: att.url) {
                                    AsyncImage(url: url) { phase in
                                        switch phase {
                                        case .success(let image):
                                            image.resizable()
                                                .aspectRatio(contentMode: .fill)
                                                .frame(width: 48, height: 48)
                                                .clipped()
                                                .cornerRadius(4)
                                        default:
                                            RoundedRectangle(cornerRadius: 4)
                                                .fill(appState.themeText.opacity(0.05))
                                                .frame(width: 48, height: 48)
                                        }
                                    }
                                } else {
                                    HStack(spacing: 4) {
                                        Image(systemName: "paperclip")
                                            .font(.system(size: 9))
                                            .foregroundColor(appState.themeText.opacity(0.4))
                                        Text(att.filename)
                                            .font(.system(size: 9))
                                            .foregroundColor(appState.themeText.opacity(0.4))
                                            .lineLimit(1)
                                    }
                                    .padding(.horizontal, 6)
                                    .padding(.vertical, 3)
                                    .background(appState.themeText.opacity(0.05))
                                    .cornerRadius(4)
                                }
                            }
                        }
                    }
                }
            }
            .padding(isMine ? .trailing : .leading, 46)
            .padding(.bottom, 4)
        }
    }

    private var hoverActions: some View {
        HStack(spacing: 2) {
            Button { onReply(msg) } label: {
                Image(systemName: "arrowshape.turn.up.left")
                    .font(.system(size: 10))
                    .foregroundColor(appState.themeText.opacity(0.7))
                    .frame(width: 24, height: 22)
                    .background(appState.themeCard)
                    .cornerRadius(4)
            }
            .buttonStyle(.plain)
            .help("Reply")

            ForEach(["👍", "❤️", "😂"], id: \.self) { emoji in
                Button { onToggleReaction(msg.id, emoji) } label: {
                    Text(emoji)
                        .font(.system(size: 11))
                        .frame(width: 24, height: 22)
                        .background(appState.themeCard)
                        .cornerRadius(4)
                }
                .buttonStyle(.plain)
            }
        }
        .padding(4)
        .onHover { if $0 { hoveredMessageId = msg.id } }
    }

    private var reactionPills: some View {
        HStack(spacing: 4) {
            ForEach(msg.reactions, id: \.emoji) { reaction in
                let mineReaction = reaction.userIds.contains(currentUserId)
                Button {
                    onToggleReaction(msg.id, reaction.emoji)
                } label: {
                    HStack(spacing: 3) {
                        Text(reaction.emoji).font(.system(size: 12))
                        if reaction.count > 1 {
                            Text("\(reaction.count)")
                                .font(.system(size: 10, weight: .medium))
                                .foregroundColor(mineReaction ? appState.themeAccent : appState.themeText.opacity(0.6))
                        }
                    }
                    .padding(.horizontal, 6)
                    .padding(.vertical, 2)
                    .background(mineReaction ? appState.themeAccent.opacity(0.2) : appState.themeText.opacity(0.08))
                    .cornerRadius(10)
                    .overlay(
                        RoundedRectangle(cornerRadius: 10)
                            .stroke(mineReaction ? appState.themeAccent.opacity(0.4) : Color.clear, lineWidth: 1)
                    )
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.top, 2)
    }

    @ViewBuilder
    private func senderAvatar(_ msg: ChannelMessage) -> some View {
        if let urlStr = msg.senderAvatarUrl, let url = URL(string: urlStr) {
            AsyncImage(url: url) { phase in
                switch phase {
                case .success(let image):
                    image
                        .resizable()
                        .aspectRatio(contentMode: .fill)
                        .frame(width: 36, height: 36)
                        .clipShape(Circle())
                default:
                    avatarFallback(msg.senderName)
                }
            }
        } else {
            avatarFallback(msg.senderName)
        }
    }

    private func avatarFallback(_ name: String) -> some View {
        let initials = name
            .split(separator: " ")
            .prefix(2)
            .compactMap { $0.first.map(String.init) }
            .joined()
            .uppercased()
        let hue = Double(abs(name.hashValue) % 360) / 360.0
        return Circle()
            .fill(Color(hue: hue, saturation: 0.55, brightness: 0.6))
            .frame(width: 36, height: 36)
            .overlay(
                Text(initials.isEmpty ? "?" : initials)
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundColor(.white)
            )
    }

    @ViewBuilder
    private func attachmentList(_ attachments: [ChannelAttachment], isMine: Bool) -> some View {
        VStack(alignment: isMine ? .trailing : .leading, spacing: 6) {
            ForEach(attachments, id: \.self) { att in
                attachmentView(att)
            }
        }
    }

    @ViewBuilder
    private func attachmentView(_ att: ChannelAttachment) -> some View {
        if att.contentType.hasPrefix("image/"), let url = URL(string: att.url) {
            // Button (not .onTapGesture) so the tap reliably wins over the
            // row's hover / contextMenu gestures.
            Button {
                onOpenAttachment(att)
            } label: {
                AsyncImage(url: url) { phase in
                    switch phase {
                    case .success(let image):
                        image
                            .resizable()
                            .aspectRatio(contentMode: .fit)
                            .frame(maxWidth: 320, maxHeight: 240)
                            .cornerRadius(6)
                    default:
                        RoundedRectangle(cornerRadius: 6)
                            .fill(appState.themeText.opacity(0.05))
                            .frame(width: 200, height: 120)
                            .overlay(ProgressView().controlSize(.small))
                    }
                }
            }
            .buttonStyle(.plain)
        } else {
            Button {
                onOpenAttachment(att)
            } label: {
                HStack(spacing: 8) {
                    Image(systemName: channelAttachmentIcon(for: att.contentType))
                        .font(.system(size: 14))
                        .foregroundColor(appState.themeAccent)
                    VStack(alignment: .leading, spacing: 1) {
                        Text(att.filename)
                            .font(.system(size: 12))
                            .foregroundColor(appState.themeText.opacity(0.85))
                            .lineLimit(1)
                            .truncationMode(.middle)
                        Text(formatSize(att.size))
                            .font(.system(size: 10))
                            .foregroundColor(appState.themeText.opacity(0.4))
                    }
                }
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                .background(appState.themeText.opacity(0.05))
                .cornerRadius(6)
            }
            .buttonStyle(.plain)
        }
    }

    private func formatSize(_ bytes: Int) -> String {
        ByteCountFormatter.string(fromByteCount: Int64(bytes), countStyle: .file)
    }

    /// True while inside the 15-minute author edit/delete window. The server
    /// enforces the same window; this only hides the affordance past it.
    private var withinEditWindow: Bool {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let date = formatter.date(from: msg.createdAt) ?? ISO8601DateFormatter().date(from: msg.createdAt)
        guard let date else { return false }
        return Date().timeIntervalSince(date) <= 15 * 60
    }

    private func formatTimestamp(_ iso: String) -> String {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let date = formatter.date(from: iso) ?? ISO8601DateFormatter().date(from: iso)
        guard let date else { return "" }
        let display = DateFormatter()
        display.dateFormat = "HH:mm"
        return display.string(from: date)
    }

    private func mentionAttributedContent(_ msg: ChannelMessage) -> AttributedString {
        var attributed = AttributedString(msg.content)
        let resolved: Set<String> = msg.mentionedUserIds.map(Set.init) ?? Set()
        // Build handle -> member map (handle = email local-part lowercased).
        let memberByHandle: [String: ChannelMember] = Dictionary(
            uniqueKeysWithValues: members.compactMap { m -> (String, ChannelMember)? in
                let local = m.email.split(separator: "@").first.map(String.init) ?? ""
                guard !local.isEmpty else { return nil }
                return (local.lowercased(), m)
            }
        )
        let pattern = #"(?<=^|\s)@([A-Za-z0-9._-]{2,32})\b"#
        guard let regex = try? NSRegularExpression(pattern: pattern) else { return attributed }
        let nsContent = msg.content as NSString
        let matches = regex.matches(in: msg.content, range: NSRange(location: 0, length: nsContent.length))
        for m in matches.reversed() {
            // Use group 1 (handle) for lookup; style the full match (with @).
            let handleRange = m.range(at: 1)
            guard handleRange.location != NSNotFound else { continue }
            let handle = nsContent.substring(with: handleRange).lowercased()
            guard let member = memberByHandle[handle] else { continue }
            // If the server stamped resolved IDs, only chip those; otherwise
            // chip every membership-resolved handle (REST-fetched older msgs).
            if !resolved.isEmpty && !resolved.contains(member.userId) { continue }
            let chipNSRange = NSRange(location: handleRange.location - 1, length: handleRange.length + 1)
            guard chipNSRange.location >= 0,
                  chipNSRange.location + chipNSRange.length <= nsContent.length,
                  let stringRange = Range(chipNSRange, in: msg.content),
                  let attrRange = Range(stringRange, in: attributed)
            else { continue }
            let isMe = member.userId == currentUserId
            attributed[attrRange].foregroundColor = isMe ? .yellow : appState.themeAccent
            attributed[attrRange].font = .system(size: 13, weight: .semibold)
        }
        return attributed
    }
}

// Shared between message row and composer.
func channelAttachmentIcon(for contentType: String) -> String {
    if contentType.hasPrefix("video/") { return "play.rectangle" }
    if contentType.hasPrefix("audio/") { return "waveform" }
    if contentType.contains("pdf") { return "doc.richtext" }
    if contentType.contains("csv") || contentType.contains("sheet") { return "tablecells" }
    if contentType.contains("word") || contentType.contains("document") { return "doc.text" }
    return "paperclip"
}
