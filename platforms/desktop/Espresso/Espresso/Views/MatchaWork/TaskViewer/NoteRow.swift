import SwiftUI

/// One note in the task feed. Leads with actor/timestamp provenance, then body,
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
    var autoPRBotUserId: String? = nil
    let onPreview: (MWProjectFile) -> Void
    var onReply: (() -> Void)? = nil

    private var isPriorRound: Bool { noteRound < currentRound }

    private var body_: String {
        (entry.metadata?["body"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private var isAutoPRAdditionalContext: Bool {
        entry.metadata?["kind"] == "autopr_additional_context"
    }

    /// Only the server-provided service-account id can mark a note automated.
    /// Display names are user-controlled and therefore never an identity signal.
    private var isAutoPRActor: Bool {
        guard let autoPRBotUserId else { return false }
        return entry.actorUserId?.lowercased() == autoPRBotUserId.lowercased()
    }

    private var actorDisplayName: String {
        if isAutoPRActor { return "matcha-autopr" }
        if let name = entry.actorName?.trimmingCharacters(in: .whitespacesAndNewlines), !name.isEmpty {
            return name
        }
        return entry.actorUserId == nil ? "System" : "Contributor"
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
                if isAutoPRActor {
                    Circle()
                        .fill(Color.mwInkStrong.opacity(0.16))
                        .frame(width: 24, height: 24)
                        .overlay(
                            Image(systemName: "cpu")
                                .font(.ticket(size: 10))
                                .foregroundColor(.mwInkStrong)
                        )
                } else if let actorId = entry.actorUserId {
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
                                .font(.ticket(size: 11))
                                .foregroundColor(.secondary)
                        )
                }
                VStack(alignment: .leading, spacing: 4) {
                    HStack(spacing: 6) {
                        Text(actorDisplayName)
                            .font(.ticket(size: 12, weight: .medium))
                            .foregroundColor(.mwInk)
                        if isAutoPRActor {
                            Text("Automated")
                                .font(.ticket(size: 10))
                                .foregroundColor(.mwInkStrong)
                                .padding(.horizontal, 4)
                                .padding(.vertical, 1)
                        }
                        Text(PacificDateFormatter.absolute(entry.createdAt) ?? "")
                            .font(.ticket(size: 10))
                            .foregroundColor(.secondary)
                        if currentRound > 1 {
                            Text("Round \(noteRound)")
                                .font(.ticket(size: 10))
                                .foregroundColor(isPriorRound ? .secondary : .mwInkStrong)
                                .padding(.horizontal, 4)
                                .padding(.vertical, 1)
                                .background((isPriorRound ? Color.secondary : Color.mwInkStrong).opacity(0.15))
                                .cornerRadius(3)
                        }
                        Spacer(minLength: 0)
                        if let onReply {
                            Button(action: onReply) {
                                Label("Reply", systemImage: "arrowshape.turn.up.left")
                                    .font(.ticket(size: 10))
                                    .foregroundColor(.mwInkStrong)
                            }
                            .buttonStyle(.plain)
                        }
                    }
                    if isAutoPRAdditionalContext {
                        Label("Additional context", systemImage: "arrow.clockwise.circle.fill")
                            .font(.ticket(size: 10))
                            .foregroundColor(.mwInkStrong)
                            .padding(.horizontal, 5)
                            .padding(.vertical, 2)
                    }
                    // Quoted parent — shows what this note is replying to.
                    if let excerpt = replyParentExcerpt {
                        HStack(spacing: 5) {
                            Rectangle()
                                .fill(Color.mwInkStrong.opacity(0.7))
                                .frame(width: 2)
                                .cornerRadius(1)
                            VStack(alignment: .leading, spacing: 0) {
                                if let name = replyParentName {
                                    Text(name)
                                        .font(.ticket(size: 10))
                                        .foregroundColor(.mwInkStrong)
                                }
                                Text(excerpt)
                                    .font(.ticket(size: 10))
                                    .foregroundColor(.secondary)
                                    .lineLimit(2)
                            }
                        }
                        .fixedSize(horizontal: false, vertical: true)
                        .padding(.leading, 1)
                    }
                    if !bodyText.isEmpty {
                        Text(bodyText)
                            .font(.ticket(size: 13))
                            .lineSpacing(3)
                            .foregroundColor(.mwInk.opacity(0.9))
                            .fixedSize(horizontal: false, vertical: true)
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
                }
                Spacer(minLength: 0)
            }
            .padding(.vertical, 6)
            .frame(maxWidth: .infinity, alignment: .leading)
            .opacity(isPriorRound ? 0.6 : 1)   // prior-round comments recede
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
                        .font(.ticket(size: 11))
                    Text(file.filename)
                        .font(.ticket(size: 10))
                        .lineLimit(1)
                        .truncationMode(.middle)
                }
                .foregroundColor(.mwInk)
                .padding(.horizontal, 8)
                .padding(.vertical, 6)
                .background(Color.mwInk.opacity(0.06))
                .cornerRadius(4)
            }
        }
        .contentShape(Rectangle())
        .onTapGesture(perform: onTap)
        .help(file.filename)
    }
}
