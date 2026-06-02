import SwiftUI

/// One event inside a round. Dispatches on `event_type` so notes render
/// rich (body + image thumbnails) while structural events render as a
/// single icon + line ("haley added subtask: 'Add EIN validation'").
struct EventRow: View {
    let event: MWTaskHistoryEntry
    let files: [MWProjectFile]
    let onPreview: (MWProjectFile) -> Void

    /// Only "ownership-meaningful" events show an avatar: notes (via NoteRow),
    /// subtask additions, ticket creation, and round openings. Status moves,
    /// reassignments, edits, and subtask state-flips revert to the original
    /// SF-Symbol-only row — the actor name in the secondary line is enough
    /// for those low-signal audit events.
    private static let avatarBearingEvents: Set<String> = [
        "created", "round_started", "subtask_added",
    ]

    var body: some View {
        if event.eventType == "activity" {
            // Notes get the full card treatment (body + actor + thumbs).
            NoteRow(entry: event, files: files, onPreview: onPreview)
        } else {
            HStack(alignment: .top, spacing: 8) {
                if Self.avatarBearingEvents.contains(event.eventType),
                   let actorId = event.actorUserId {
                    ChannelAvatarView(
                        senderId: actorId,
                        payloadURL: event.actorAvatarUrl,
                        name: event.actorName ?? "",
                        size: 22
                    )
                } else {
                    Image(systemName: Self.icon(for: event.eventType))
                        .font(.system(size: 11))
                        .foregroundColor(Self.tint(for: event.eventType))
                        .frame(width: 22, alignment: .center)
                }
                VStack(alignment: .leading, spacing: 1) {
                    Text(Self.describe(event))
                        .font(.system(size: 11))
                        .foregroundColor(.white.opacity(0.9))
                        .fixedSize(horizontal: false, vertical: true)
                    Text(PacificDateFormatter.absolute(event.createdAt) ?? event.createdAt)
                        .font(.system(size: 9))
                        .foregroundColor(.secondary)
                }
                Spacer(minLength: 0)
            }
            .padding(.vertical, 1)
        }
    }

    static func icon(for event: String) -> String {
        switch event {
        case "created": return "plus.circle.fill"
        case "column_change": return "arrow.right.circle"
        case "assignee_change": return "person.circle"
        case "description_change": return "text.alignleft"
        case "progress_note_change": return "note.text"
        case "review_rejected": return "arrow.uturn.backward.circle"
        case "round_started": return "flag.circle.fill"
        case "subtask_added": return "plus.square"
        case "subtask_completed": return "checkmark.square.fill"
        case "subtask_uncompleted": return "square"
        case "subtask_deleted": return "trash"
        case "deleted": return "trash.circle"
        default: return "circle"
        }
    }

    static func tint(for event: String) -> Color {
        switch event {
        case "created": return .matcha500
        case "column_change": return .matcha500
        case "assignee_change": return .blue
        case "description_change": return .matcha500
        case "progress_note_change": return .matcha500
        case "review_rejected": return .orange
        case "round_started": return .matcha500
        case "subtask_added": return .blue
        case "subtask_completed": return .matcha500
        case "subtask_uncompleted": return .orange
        case "subtask_deleted": return .red
        case "deleted": return .red
        default: return .secondary
        }
    }

    static func describe(_ e: MWTaskHistoryEntry) -> String {
        let who = (e.actorName?.isEmpty == false ? e.actorName! : "Someone")
        switch e.eventType {
        case "created":
            return "\(who) created this task" + (e.toValue.map { " in \(columnLabel($0))" } ?? "")
        case "column_change":
            let from = e.fromValue.map { columnLabel($0) } ?? "?"
            let to = e.toValue.map { columnLabel($0) } ?? "?"
            return "\(who) moved \(from) → \(to)"
        case "assignee_change":
            if e.toValue == nil { return "\(who) unassigned this task" }
            return "\(who) updated the assignee"
        case "description_change":
            return "\(who) updated the description"
        case "progress_note_change":
            return "\(who) updated where we're at"
        case "review_rejected":
            let note = (e.metadata?["note"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            return note.isEmpty
                ? "\(who) sent this back for changes"
                : "\(who) sent back: \u{201C}\(note)\u{201D}"
        case "round_started":
            let title = (e.metadata?["title"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            return title.isEmpty
                ? "\(who) opened a new round"
                : "\(who) opened a new round: \u{201C}\(title)\u{201D}"
        case "subtask_added":
            let title = (e.metadata?["title"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            return title.isEmpty
                ? "\(who) added a checklist item"
                : "\(who) added: \u{201C}\(title)\u{201D}"
        case "subtask_completed":
            let title = (e.metadata?["title"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            return title.isEmpty
                ? "\(who) completed a checklist item"
                : "\(who) completed: \u{201C}\(title)\u{201D}"
        case "subtask_uncompleted":
            let title = (e.metadata?["title"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            return title.isEmpty
                ? "\(who) reopened a checklist item"
                : "\(who) reopened: \u{201C}\(title)\u{201D}"
        case "subtask_deleted":
            let title = (e.metadata?["title"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            return title.isEmpty
                ? "\(who) removed a checklist item"
                : "\(who) removed: \u{201C}\(title)\u{201D}"
        case "deleted":
            return "\(who) deleted this task"
        default:
            return "\(who) \(e.eventType)"
        }
    }

    private static func columnLabel(_ raw: String) -> String {
        raw.replacingOccurrences(of: "_", with: " ").capitalized
    }
}
