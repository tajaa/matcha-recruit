import SwiftUI
import AppKit

/// One checklist row in the TaskViewerSheet: toggle checkbox + title, delete on
/// hover. Done items strike through and dim. Dark-themed to match the sheet.
struct SubtaskRow: View {
    let item: MWSubtask
    let collaborators: [MWProjectCollaborator]
    let currentUserId: String?
    let onToggle: () -> Void
    let onDelete: () -> Void
    let onAssign: (String?) -> Void
    @State private var isHovered = false
    @State private var showingAssign = false

    private var assignee: MWProjectCollaborator? {
        guard let id = item.assignedTo else { return nil }
        return collaborators.first { $0.userId == id }
    }

    var body: some View {
        HStack(spacing: 8) {
            Button(action: onToggle) {
                Image(systemName: item.isDone ? "checkmark.circle.fill" : "circle")
                    .font(.system(size: 13))
                    .foregroundColor(item.isDone ? .matcha500 : .secondary)
            }
            .buttonStyle(.plain)
            Text(item.title)
                .font(.system(size: 12))
                .foregroundColor(item.isDone ? .secondary : .white)
                .strikethrough(item.isDone)
                .lineLimit(2)
                .multilineTextAlignment(.leading)
                .textSelection(.enabled)
                .contextMenu {
                    Button("Copy") {
                        NSPasteboard.general.clearContents()
                        NSPasteboard.general.setString(item.title, forType: .string)
                    }
                }
            Spacer(minLength: 0)
            assigneeMenu
            if isHovered {
                Button(action: onDelete) {
                    Image(systemName: "trash")
                        .font(.system(size: 10))
                        .foregroundColor(.red.opacity(0.8))
                }
                .buttonStyle(.plain)
                .help("Delete item")
            }
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 5)
        .background(isHovered ? Color.zinc800.opacity(0.6) : Color.clear)
        .cornerRadius(4)
        .contentShape(Rectangle())
        .onHover { isHovered = $0 }
    }

    // A plain Button (NOT a Menu label) — macOS Menu labels rasterize a
    // resizable image oddly (clipShape ignored → square/garbled avatar). A
    // Button renders ChannelAvatarView as the same clean 18×18 circle it shows
    // in the discussion feed. The picker is a confirmationDialog.
    private var assigneeMenu: some View {
        Button { showingAssign = true } label: {
            if let id = item.assignedTo {
                ChannelAvatarView(
                    senderId: id,
                    payloadURL: assignee?.avatarUrl,
                    name: assignee?.name ?? "",
                    size: 18
                )
            } else {
                Circle()
                    .strokeBorder(Color.secondary.opacity(isHovered ? 0.7 : 0.35),
                                  style: StrokeStyle(lineWidth: 1, dash: [2, 2]))
                    .frame(width: 18, height: 18)
                    .overlay(
                        Image(systemName: "plus")
                            .symbolRenderingMode(.monochrome)
                            .font(.system(size: 9, weight: .semibold))
                            .foregroundColor(.secondary.opacity(isHovered ? 0.9 : 0.45))
                    )
            }
        }
        .buttonStyle(.plain)
        .help(assignee?.name ?? "Assign")
        .confirmationDialog("Assign checklist item", isPresented: $showingAssign, titleVisibility: .visible) {
            if let uid = currentUserId, uid != item.assignedTo {
                Button("Assign to me") { onAssign(uid) }
            }
            ForEach(collaborators) { c in
                Button(c.userId == item.assignedTo ? "✓ \(c.name)" : c.name) { onAssign(c.userId) }
            }
            if item.assignedTo != nil {
                Button("Unassign", role: .destructive) { onAssign(nil) }
            }
            Button("Cancel", role: .cancel) {}
        }
    }
}
