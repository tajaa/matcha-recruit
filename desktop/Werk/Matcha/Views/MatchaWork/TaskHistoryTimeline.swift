import SwiftUI

/// Inline chronological timeline of `mw_task_history` rows for one task.
/// Rendered inside `TaskViewerSheet` between description and attachments.
/// Server returns rows oldest-first; we keep that order so the reader sees
/// creation at the top and recent moves at the bottom.
struct TaskHistoryTimeline: View {
    let entries: [MWTaskHistoryEntry]

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 6) {
                Image(systemName: "clock")
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
                Text("HISTORY")
                    .font(.system(size: 9, weight: .semibold))
                    .foregroundColor(.secondary)
                    .tracking(0.5)
                Text("\(entries.count)")
                    .font(.system(size: 9))
                    .foregroundColor(.secondary)
                    .padding(.horizontal, 5)
                    .padding(.vertical, 1)
                    .background(Color.zinc800)
                    .cornerRadius(4)
            }
            VStack(alignment: .leading, spacing: 4) {
                ForEach(entries) { e in
                    HStack(alignment: .top, spacing: 8) {
                        Image(systemName: Self.icon(for: e.eventType))
                            .font(.system(size: 10))
                            .foregroundColor(Self.tint(for: e.eventType))
                            .frame(width: 14, alignment: .center)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(Self.describe(e))
                                .font(.system(size: 11))
                                .foregroundColor(.white.opacity(0.9))
                                .multilineTextAlignment(.leading)
                                .fixedSize(horizontal: false, vertical: true)
                            Text(Self.relativeDate(e.createdAt))
                                .font(.system(size: 9))
                                .foregroundColor(.secondary)
                        }
                        Spacer(minLength: 0)
                    }
                    .padding(.vertical, 2)
                }
            }
            .padding(8)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.zinc800.opacity(0.4))
            .cornerRadius(6)
        }
    }

    private static func icon(for event: String) -> String {
        switch event {
        case "created": return "plus.circle.fill"
        case "column_change": return "arrow.right.circle"
        case "assignee_change": return "person.circle"
        case "description_change": return "text.alignleft"
        case "progress_note_change": return "note.text"
        case "deleted": return "trash.circle"
        default: return "circle"
        }
    }

    private static func tint(for event: String) -> Color {
        switch event {
        case "created": return .matcha500
        case "column_change": return .matcha500
        case "assignee_change": return .blue
        case "description_change": return .matcha500
        case "progress_note_change": return .matcha500
        case "deleted": return .red
        default: return .secondary
        }
    }

    private static func describe(_ e: MWTaskHistoryEntry) -> String {
        let who = (e.actorName?.isEmpty == false ? e.actorName! : "Someone")
        switch e.eventType {
        case "created":
            return "\(who) created this task" + (e.toValue.map { " in \(columnLabel($0))" } ?? "")
        case "column_change":
            let from = e.fromValue.map { columnLabel($0) } ?? "?"
            let to = e.toValue.map { columnLabel($0) } ?? "?"
            return "\(who) moved \(from) → \(to)"
        case "assignee_change":
            if e.toValue == nil {
                return "\(who) unassigned this task"
            }
            return "\(who) updated the assignee"
        case "description_change":
            return "\(who) updated the description"
        case "progress_note_change":
            return "\(who) updated where we're at"
        case "deleted":
            return "\(who) deleted this task"
        default:
            return "\(who) \(e.eventType)"
        }
    }

    private static func columnLabel(_ raw: String) -> String {
        raw.replacingOccurrences(of: "_", with: " ").capitalized
    }

    private static func relativeDate(_ iso: String) -> String {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let date: Date? = formatter.date(from: iso) ?? {
            formatter.formatOptions = [.withInternetDateTime]
            return formatter.date(from: iso)
        }()
        guard let d = date else { return iso }
        let rel = RelativeDateTimeFormatter()
        rel.unitsStyle = .short
        return rel.localizedString(for: d, relativeTo: Date())
    }
}
