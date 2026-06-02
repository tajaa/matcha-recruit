import SwiftUI

/// One note in the task feed. Renders body + actor/timestamp footer plus
/// (when the note has linked file ids) a row of inline image thumbnails
/// resolved from the task's uploaded files. Tap a thumbnail to open the
/// existing AttachmentPreviewSheet.
struct NoteRow: View {
    let entry: MWTaskHistoryEntry
    let files: [MWProjectFile]
    /// The round this comment was posted in, and the ticket's live round.
    /// When they differ the row is chipped + dimmed so a prior-round comment
    /// never reads as part of the current round. Default 1/1 (e.g. EventRow's
    /// inline use) renders no chip.
    var noteRound: Int = 1
    var currentRound: Int = 1
    let onPreview: (MWProjectFile) -> Void
    var onReply: (() -> Void)? = nil
    @State private var isHovered = false

    private var isPriorRound: Bool { noteRound < currentRound }

    private var body_: String {
        (entry.metadata?["body"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private var linkedFiles: [MWProjectFile] {
        guard let ids = entry.attachmentIds, !ids.isEmpty else { return [] }
        let idSet = Set(ids)
        return files.filter { idSet.contains($0.id) }
    }

    /// Set on notes that reply to an earlier comment — resolved server-side and
    /// stashed in metadata so we can render the quoted parent inline.
    private var replyParentName: String? { entry.metadata?["reply_to_name"] }
    private var replyParentExcerpt: String? {
        let e = (entry.metadata?["reply_to_excerpt"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        return e.isEmpty ? nil : e
    }

    var body: some View {
        let bodyText = body_
        let linked = linkedFiles
        if bodyText.isEmpty && linked.isEmpty { EmptyView() } else {
            HStack(alignment: .top, spacing: 8) {
                // Per-note avatar on the LEFT so a row of stacked notes
                // reads like a chat thread — eye drops down the avatar
                // column to identify who wrote what without parsing the
                // actor name in the footer.
                if let actorId = entry.actorUserId {
                    ChannelAvatarView(
                        senderId: actorId,
                        payloadURL: entry.actorAvatarUrl,
                        name: entry.actorName ?? "",
                        size: 24
                    )
                } else {
                    // System-generated notes are rare; keep a neutral
                    // grey circle so the row still aligns.
                    Circle()
                        .fill(Color.zinc800)
                        .frame(width: 24, height: 24)
                        .overlay(
                            Image(systemName: "text.bubble")
                                .font(.system(size: 11))
                                .foregroundColor(.secondary)
                        )
                }
                VStack(alignment: .leading, spacing: 4) {
                    // Quoted parent — shows what this note is replying to.
                    if let excerpt = replyParentExcerpt {
                        HStack(spacing: 5) {
                            Rectangle()
                                .fill(Color.matcha500.opacity(0.7))
                                .frame(width: 2)
                                .cornerRadius(1)
                            VStack(alignment: .leading, spacing: 0) {
                                if let name = replyParentName {
                                    Text(name)
                                        .font(.system(size: 8, weight: .semibold))
                                        .foregroundColor(.matcha500)
                                }
                                Text(excerpt)
                                    .font(.system(size: 10))
                                    .foregroundColor(.secondary)
                                    .lineLimit(2)
                            }
                        }
                        .padding(.leading, 1)
                    }
                    if !bodyText.isEmpty {
                        Text(bodyText)
                            .font(.system(size: 12))
                            .foregroundColor(.white.opacity(0.9))
                            .textSelection(.enabled)
                    }
                    if !linked.isEmpty {
                        ScrollView(.horizontal, showsIndicators: false) {
                            HStack(spacing: 6) {
                                ForEach(linked) { f in
                                    NoteAttachmentThumb(file: f) { onPreview(f) }
                                }
                            }
                        }
                    }
                    HStack(spacing: 8) {
                        Text("\((entry.actorName?.isEmpty == false ? entry.actorName! : "Someone")) · \(PacificDateFormatter.absolute(entry.createdAt) ?? "")")
                            .font(.system(size: 9))
                            .foregroundColor(.secondary)
                        // Which round this comment is from. Only shown on
                        // multi-round tickets; greyed for prior rounds, matcha
                        // for the current one.
                        if currentRound > 1 {
                            Text("Round \(noteRound)")
                                .font(.system(size: 8, weight: .semibold))
                                .foregroundColor(isPriorRound ? .secondary : .matcha500)
                                .padding(.horizontal, 4)
                                .padding(.vertical, 1)
                                .background((isPriorRound ? Color.secondary : Color.matcha500).opacity(0.15))
                                .cornerRadius(3)
                        }
                        if let onReply, isHovered {
                            Button(action: onReply) {
                                HStack(spacing: 2) {
                                    Image(systemName: "arrowshape.turn.up.left")
                                        .font(.system(size: 8))
                                    Text("Reply")
                                        .font(.system(size: 9, weight: .semibold))
                                }
                                .foregroundColor(.matcha500)
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }
                Spacer(minLength: 0)
            }
            .padding(8)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.zinc800.opacity(0.5))
            .cornerRadius(5)
            .opacity(isPriorRound ? 0.6 : 1)   // prior-round comments recede
            .onHover { isHovered = $0 }
        }
    }
}

/// Inline thumbnail rendered inside a NoteRow for each linked file.
/// Images load remotely via AsyncImage; non-images fall back to a doc
/// icon + filename chip.
private struct NoteAttachmentThumb: View {
    let file: MWProjectFile
    let onTap: () -> Void

    var body: some View {
        Group {
            if file.isImage, let url = URL(string: file.storageUrl) {
                AsyncImage(url: url) { phase in
                    switch phase {
                    case .success(let img):
                        img.resizable()
                            .interpolation(.medium)
                            .aspectRatio(contentMode: .fill)
                    case .failure:
                        Image(systemName: "photo")
                            .foregroundColor(.secondary)
                    default:
                        ProgressView().controlSize(.small)
                    }
                }
                .frame(width: 92, height: 64)
                .clipShape(RoundedRectangle(cornerRadius: 4))
                .overlay(
                    RoundedRectangle(cornerRadius: 4)
                        .stroke(Color.zinc800, lineWidth: 1)
                )
            } else {
                HStack(spacing: 4) {
                    Image(systemName: "doc")
                        .font(.system(size: 11))
                    Text(file.filename)
                        .font(.system(size: 10))
                        .lineLimit(1)
                        .truncationMode(.middle)
                }
                .foregroundColor(.white)
                .padding(.horizontal, 8)
                .padding(.vertical, 6)
                .background(Color.zinc800)
                .cornerRadius(4)
            }
        }
        .contentShape(Rectangle())
        .onTapGesture(perform: onTap)
        .help(file.filename)
    }
}
