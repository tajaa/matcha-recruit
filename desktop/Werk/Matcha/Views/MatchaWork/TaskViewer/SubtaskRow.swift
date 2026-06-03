import SwiftUI
import AppKit

/// One checklist row in the TaskViewerSheet: toggle checkbox + title, delete on
/// hover. Done items strike through and dim. Dark-themed to match the sheet.
struct SubtaskRow: View {
    @Environment(AppState.self) private var appState
    let item: MWSubtask
    let collaborators: [MWProjectCollaborator]
    let currentUserId: String?
    let onToggle: () -> Void
    let onDelete: () -> Void
    let onAssign: (String?) -> Void
    /// When the ticket is in review, a reviewer can DENY a completed item —
    /// reopen it with a reason + severity (audited as `subtask_rejected`).
    var canReview: Bool = false
    var onDeny: ((String, String?) -> Void)? = nil
    /// Set when this item was added by someone other than the assignee (new
    /// scope, usually the reviewer) — shows an "added by <name>" chip.
    var addedByName: String? = nil
    @State private var isHovered = false
    @State private var showingAssign = false
    @State private var showDeny = false
    @State private var denyReason = ""
    @State private var denySeverity = "blocker"
    @FocusState private var denyFocused: Bool

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
                .foregroundColor(item.isDone ? appState.themeTextSecondary : appState.themeText)
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
            if let by = addedByName {
                HStack(spacing: 2) {
                    Image(systemName: "person.badge.plus").font(.system(size: 7))
                    Text("added by \(by)").font(.system(size: 8, weight: .medium))
                }
                .foregroundColor(.blue)
                .padding(.horizontal, 4).padding(.vertical, 1)
                .background(Color.blue.opacity(0.15)).cornerRadius(3)
                .help("Added during review by \(by) — new scope, not part of your original checklist")
            }
            Spacer(minLength: 0)
            if canReview && item.isDone, onDeny != nil {
                denyButton
            }
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
        .background(isHovered ? appState.themeText.opacity(0.06) : Color.clear)
        .cornerRadius(4)
        .contentShape(Rectangle())
        .onHover { isHovered = $0 }
    }

    /// Deny = reopen a completed item with a reason. Orange ✗ → reason popover.
    private var denyButton: some View {
        Button { showDeny = true } label: {
            Image(systemName: "xmark.circle")
                .font(.system(size: 11))
                .foregroundColor(.orange.opacity(0.85))
        }
        .buttonStyle(.plain)
        .help("Deny — reopen this item with a reason for the assignee")
        .popover(isPresented: $showDeny, arrowEdge: .bottom) {
            VStack(alignment: .leading, spacing: 8) {
                Text("Deny completion")
                    .font(.system(size: 11, weight: .semibold)).foregroundColor(appState.themeText)
                Text("\u{201C}\(item.title)\u{201D}")
                    .font(.system(size: 10)).italic().foregroundColor(appState.themeTextSecondary).lineLimit(2)
                Picker("", selection: $denySeverity) {
                    Text("Blocker").tag("blocker")
                    Text("Nit").tag("nit")
                }
                .pickerStyle(.segmented)
                .labelsHidden()
                TextField("Why isn't this actually done?", text: $denyReason, axis: .vertical)
                    .textFieldStyle(.plain).font(.system(size: 12)).foregroundColor(appState.themeText)
                    .lineLimit(1...4).padding(8).background(appState.themeText.opacity(0.06)).cornerRadius(6)
                    .focused($denyFocused)
                HStack {
                    Spacer()
                    Button("Cancel") { showDeny = false; denyReason = "" }
                        .buttonStyle(.plain).font(.system(size: 11)).foregroundColor(.secondary)
                    let empty = denyReason.trimmingCharacters(in: .whitespaces).isEmpty
                    Button("Deny") {
                        onDeny?(denyReason.trimmingCharacters(in: .whitespacesAndNewlines), denySeverity)
                        showDeny = false; denyReason = ""
                    }
                    .buttonStyle(.plain).font(.system(size: 11, weight: .semibold))
                    .foregroundColor(.white).padding(.horizontal, 10).padding(.vertical, 4)
                    .background(empty ? appState.themeText.opacity(0.12) : Color.orange).cornerRadius(5)
                    .disabled(empty)
                }
            }
            .padding(12).frame(width: 260)
            .background(appState.themeCard)
            .onAppear { DispatchQueue.main.async { denyFocused = true } }
        }
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
