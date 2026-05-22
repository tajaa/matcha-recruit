import SwiftUI
import UniformTypeIdentifiers

struct ChannelMessageComposer: View {
    @Environment(AppState.self) private var appState
    let channelId: String
    let channelSlug: String
    let userHandle: String
    let members: [ChannelMember]
    let currentUserId: String
    let maxAttachments: Int
    let typingPing: () -> Void
    let onSend: () -> Void
    let onOpenFilePicker: () -> Void
    let onPasteImage: () -> Void
    @Binding var inputText: String
    @Binding var pendingAttachments: [PendingChannelAttachment]
    @Binding var replyingTo: ChannelMessage?
    @Binding var editingMessage: ChannelMessage?
    @Binding var isUploading: Bool
    @Binding var lastTypingSentAt: Date

    var body: some View {
        VStack(spacing: 8) {
            // Editing banner — mirrors the reply banner; cancel clears the draft.
            if editingMessage != nil {
                HStack(spacing: 8) {
                    Image(systemName: "pencil")
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundColor(appState.themeAccent)
                    Text("Editing message")
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundColor(appState.themeAccent)
                    Spacer()
                    Button {
                        editingMessage = nil
                        inputText = ""
                    } label: {
                        Image(systemName: "xmark")
                            .font(.system(size: 9, weight: .bold))
                            .foregroundColor(appState.themeText.opacity(0.4))
                    }
                    .buttonStyle(.plain)
                }
                .padding(.horizontal, 4)
            }

            // Reply banner
            if let reply = replyingTo {
                HStack(spacing: 8) {
                    RoundedRectangle(cornerRadius: 1)
                        .fill(appState.themeAccent)
                        .frame(width: 3, height: 24)
                    VStack(alignment: .leading, spacing: 1) {
                        Text("Replying to \(reply.senderName)")
                            .font(.system(size: 10, weight: .semibold))
                            .foregroundColor(appState.themeAccent)
                        Text(reply.content.isEmpty ? (reply.attachments.isEmpty ? "" : "📎 attachment") : String(reply.content.prefix(80)))
                            .font(.system(size: 10))
                            .foregroundColor(appState.themeText.opacity(0.5))
                            .lineLimit(1)
                    }
                    Spacer()
                    Button { replyingTo = nil } label: {
                        Image(systemName: "xmark")
                            .font(.system(size: 9, weight: .bold))
                            .foregroundColor(appState.themeText.opacity(0.4))
                    }
                    .buttonStyle(.plain)
                }
                .padding(.horizontal, 4)
            }

            if !pendingAttachments.isEmpty {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 6) {
                        ForEach(pendingAttachments) { att in
                            pendingChip(att)
                        }
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }

            // Mention autocomplete — appears above the input when the user
            // has an open @-token at the end of their text and there are
            // matching channel members.
            if activeMentionQuery != nil && !mentionMatches.isEmpty {
                VStack(spacing: 0) {
                    HStack {
                        Text("MENTION")
                            .font(.system(size: 9, weight: .semibold))
                            .tracking(1.2)
                            .foregroundColor(appState.themeText.opacity(0.35))
                        Spacer()
                        Text("Click to insert")
                            .font(.system(size: 9))
                            .foregroundColor(appState.themeText.opacity(0.25))
                    }
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    Divider().opacity(0.3)
                    ForEach(Array(mentionMatches.enumerated()), id: \.element.userId) { idx, member in
                        let handle = member.email.split(separator: "@").first.map(String.init) ?? ""
                        Button { applyMention(member) } label: {
                            HStack {
                                Text(member.name)
                                    .font(.system(size: 12))
                                    .foregroundColor(appState.themeText.opacity(0.9))
                                Spacer()
                                Text("@\(handle)")
                                    .font(.system(size: 11))
                                    .foregroundColor(appState.themeAccent)
                            }
                            .padding(.horizontal, 10)
                            .padding(.vertical, 6)
                            .background(idx == 0 ? appState.themeText.opacity(0.05) : Color.clear)
                        }
                        .buttonStyle(.plain)
                    }
                }
                .background(.regularMaterial)
                .overlay(
                    RoundedRectangle(cornerRadius: 6)
                        .stroke(appState.themeBorder, lineWidth: 1)
                )
                .clipShape(RoundedRectangle(cornerRadius: 6))
                .frame(maxWidth: 320, alignment: .leading)
                .frame(maxWidth: .infinity, alignment: .leading)
            }

            HStack(alignment: .center, spacing: 8) {
                Text("\(userHandle)@\(channelSlug) ›")
                    .font(.system(size: 11))
                    .foregroundColor(appState.themeText.opacity(0.45))
                    .fixedSize()

                Button(action: onOpenFilePicker) {
                    Image(systemName: "paperclip")
                        .font(.system(size: 12))
                        .foregroundColor(appState.themeText.opacity(0.55))
                }
                .buttonStyle(.plain)
                .help("Attach files (max \(maxAttachments), 10 MB each)")
                .disabled(pendingAttachments.count >= maxAttachments || isUploading)

                Button(action: onPasteImage) {
                    Image(systemName: "photo.on.rectangle")
                        .font(.system(size: 12))
                        .foregroundColor(appState.themeText.opacity(0.55))
                }
                .buttonStyle(.plain)
                .help("Paste image from clipboard (⌃⌘⇧4 to screenshot)")
                .disabled(pendingAttachments.count >= maxAttachments || isUploading)

                TextField(
                    "",
                    text: $inputText,
                    prompt: Text("type a message (⌘↵ to send)").foregroundColor(appState.themeText.opacity(0.2)),
                    axis: .vertical
                )
                .textFieldStyle(.plain)
                .font(.system(size: 13))
                .foregroundColor(appState.themeText.opacity(0.9))
                .lineLimit(1...8)
                .onChange(of: inputText) {
                    guard !inputText.isEmpty else { return }
                    let now = Date()
                    if now.timeIntervalSince(lastTypingSentAt) >= 2.5 {
                        lastTypingSentAt = now
                        typingPing()
                    }
                }
                // No .onSubmit — Enter inserts a newline (vertical-axis field).
                // Send via the ↵ button / ⌘↵ shortcut below.

                let canSend = (!inputText.trimmingCharacters(in: .whitespaces).isEmpty || !pendingAttachments.isEmpty) && !isUploading
                Button(action: onSend) {
                    if isUploading {
                        ProgressView().controlSize(.small)
                    } else {
                        Text("↵")
                            .font(.system(size: 14, weight: .medium))
                            .foregroundColor(canSend ? appState.themeAccent : appState.themeText.opacity(0.2))
                    }
                }
                .buttonStyle(.plain)
                .disabled(!canSend)
                .keyboardShortcut(.return, modifiers: .command)
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .background(.regularMaterial)
        // Best-effort ⌘V of an image; scoped to image UTTypes so text paste
        // still goes to the TextField. The paste button is the primary path.
        .onPasteCommand(of: [.png, .tiff]) { _ in onPasteImage() }
    }

    private func pendingChip(_ att: PendingChannelAttachment) -> some View {
        HStack(spacing: 6) {
            if att.isImage, let nsImage = NSImage(data: att.data) {
                Image(nsImage: nsImage)
                    .resizable()
                    .aspectRatio(contentMode: .fill)
                    .frame(width: 28, height: 28)
                    .clipped()
                    .cornerRadius(4)
            } else {
                Image(systemName: channelAttachmentIcon(for: att.mimeType))
                    .font(.system(size: 12))
                    .foregroundColor(appState.themeAccent)
                    .frame(width: 28, height: 28)
                    .background(appState.themeText.opacity(0.05))
                    .cornerRadius(4)
            }
            Text(att.filename)
                .font(.system(size: 11))
                .foregroundColor(appState.themeText.opacity(0.75))
                .lineLimit(1)
                .truncationMode(.middle)
                .frame(maxWidth: 140)
            Button {
                pendingAttachments.removeAll { $0.id == att.id }
            } label: {
                Image(systemName: "xmark")
                    .font(.system(size: 9, weight: .bold))
                    .foregroundColor(appState.themeText.opacity(0.5))
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .background(appState.themeText.opacity(0.06))
        .cornerRadius(6)
    }

    // MARK: - Mention autocomplete

    /// Returns the active @-token under the cursor — caller passes the full
    /// inputText since SwiftUI TextEditor doesn't expose selection. We fall
    /// back to "the last @-token in the text" which is good enough for typing
    /// at the end (the dominant case); editing mid-text won't trigger
    /// autocomplete reliably but also won't misfire.
    private var activeMentionQuery: (query: String, tokenStart: String.Index)? {
        guard let atIdx = inputText.lastIndex(of: "@") else { return nil }
        // Token must be at start-of-string or preceded by whitespace.
        if atIdx > inputText.startIndex {
            let prev = inputText[inputText.index(before: atIdx)]
            if !prev.isWhitespace { return nil }
        }
        let after = inputText.index(after: atIdx)
        let q = String(inputText[after...])
        // Reject if any whitespace inside (token closed) or invalid char.
        guard !q.contains(where: { $0.isWhitespace }) else { return nil }
        guard q.count <= 32, q.allSatisfy({ $0.isLetter || $0.isNumber || "._-".contains($0) }) else { return nil }
        return (q, after)
    }

    private var mentionMatches: [ChannelMember] {
        guard let q = activeMentionQuery?.query.lowercased() else { return [] }
        return members
            .filter { $0.userId != currentUserId }
            .filter { m in
                let handle = m.email.split(separator: "@").first.map { $0.lowercased() } ?? ""
                return handle.hasPrefix(q) || m.name.lowercased().hasPrefix(q)
            }
            .prefix(6)
            .map { $0 }
    }

    private func applyMention(_ member: ChannelMember) {
        guard let active = activeMentionQuery else { return }
        let handle = member.email.split(separator: "@").first.map(String.init) ?? ""
        guard !handle.isEmpty else { return }
        let head = String(inputText[..<active.tokenStart])
        let tail = String(inputText[inputText.index(active.tokenStart, offsetBy: active.query.count)...])
        inputText = head + handle + " " + tail
    }
}
