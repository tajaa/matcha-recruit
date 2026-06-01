import SwiftUI

struct KanbanCardView: View {
    @Environment(AppState.self) private var appState
    let task: MWProjectTask
    let attachments: [MWProjectFile]
    var pipelineMode: Bool = false
    /// Element label resolved by the board (task.elementName from the list
    /// query, with a client-side fallback so freshly created/edited cards show
    /// it before the next full reload).
    var elementName: String? = nil
    let onTap: () -> Void
    let onToggle: () -> Void
    let onMoveColumn: (String) -> Void

    /// "Company · Contact" for the card face (pipeline mode); nil when neither set.
    private var contactDisplay: String? {
        let parts = [task.contactCompany, task.contactName]
            .compactMap { $0?.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
        return parts.isEmpty ? nil : parts.joined(separator: " · ")
    }

    private var imageAttachments: [MWProjectFile] { attachments.filter { $0.isImage } }
    private var nonImageCount: Int { attachments.count - imageAttachments.count }

    private var priorityColor: Color {
        switch task.priority {
        case "critical": return .red
        case "high": return .orange
        case "medium": return .yellow
        default: return .secondary
        }
    }

    private var currentColumnLabel: String {
        columnsFor(pipeline: pipelineMode).first(where: { $0.key == task.boardColumn })?.label ?? task.boardColumn
    }

    private var assigneeDisplay: String? { task.displayAssignee }

    private var assigneeInitial: String? {
        guard let name = assigneeDisplay, !name.isEmpty else { return nil }
        return String(name.prefix(1)).uppercased()
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Header band — checkbox + title. Tints orange after 6h / red after
            // 12h of inactivity (anchor = lastMovedAt ?? createdAt); never for
            // done/completed cards. See MWProjectTask.aging.
            HStack(alignment: .top, spacing: 8) {
                // Pipeline deals use the Won/Lost outcome, not task completion —
                // the checkbox would shove the card into 'done' (an orphan stage
                // here). Hide it in pipeline mode.
                if !pipelineMode {
                    Button(action: onToggle) {
                        Image(systemName: task.status == "completed" ? "checkmark.circle.fill" : "circle")
                            .font(.system(size: 13))
                            .foregroundColor(task.status == "completed" ? .matcha500 : .secondary)
                    }
                    .buttonStyle(.plain)
                }

                Text(task.title)
                    .font(.system(size: 12))
                    .foregroundColor(appState.themeText)
                    .strikethrough(task.status == "completed")
                    .lineLimit(3)
                    .multilineTextAlignment(.leading)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .padding(8)
            .background(headerTint)

            VStack(alignment: .leading, spacing: 3) {
                if let note = task.progressNote, !note.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                    HStack(spacing: 4) {
                        Image(systemName: "location.north.line")
                            .font(.system(size: 8))
                            .foregroundColor(appState.themeAccent)
                        Text(note)
                            .font(.system(size: 10))
                            .italic()
                            .foregroundColor(appState.themeText.opacity(0.6))
                            .lineLimit(1)
                    }
                }

                // Why it bounced — surfaced on the card face while it sits in
                // the rework lane, so you don't have to open the card to know.
                if task.boardColumn == "changes_requested",
                   let rnote = task.reviewNote?.trimmingCharacters(in: .whitespacesAndNewlines),
                   !rnote.isEmpty {
                    HStack(spacing: 4) {
                        Image(systemName: "arrow.uturn.backward")
                            .font(.system(size: 8))
                            .foregroundColor(.orange)
                        Text(rnote)
                            .font(.system(size: 10))
                            .foregroundColor(.orange.opacity(0.85))
                            .lineLimit(2)
                    }
                }

                if pipelineMode, let contact = contactDisplay {
                    HStack(spacing: 4) {
                        Image(systemName: "building.2")
                            .font(.system(size: 8))
                            .foregroundColor(.secondary)
                        Text(contact)
                            .font(.system(size: 10))
                            .foregroundColor(appState.themeText.opacity(0.7))
                            .lineLimit(1)
                    }
                }

                HStack(spacing: 5) {
                    Circle().fill(priorityColor).frame(width: 5, height: 5)

                    // Review churn — how many times this card has been kicked
                    // back. Only shows once it's bounced at least once.
                    if let cycles = task.reviewCycleCount, cycles > 0 {
                        HStack(spacing: 1) {
                            Image(systemName: "arrow.triangle.2.circlepath").font(.system(size: 7))
                            Text("×\(cycles)").font(.system(size: 8, weight: .bold))
                        }
                        .foregroundColor(.orange)
                        .padding(.horizontal, 4)
                        .padding(.vertical, 1)
                        .background(Color.orange.opacity(0.15))
                        .cornerRadius(3)
                        .help("Sent back from review \(cycles) time\(cycles == 1 ? "" : "s")")
                    }

                    if pipelineMode {
                        if let dv = task.dealValue, dv > 0 {
                            Text(formatDealValue(dv))
                                .font(.system(size: 9, weight: .bold))
                                .foregroundColor(appState.themeAccent)
                        }
                        if task.dealOutcome != "open" {
                            Text(task.dealOutcome.capitalized)
                                .font(.system(size: 8, weight: .semibold))
                                .foregroundColor(task.dealOutcome == "won" ? .green : .red)
                                .padding(.horizontal, 4)
                                .padding(.vertical, 1)
                                .background((task.dealOutcome == "won" ? Color.green : Color.red).opacity(0.15))
                                .cornerRadius(3)
                        }
                    }

                    Menu {
                        ForEach(columnsFor(pipeline: pipelineMode), id: \.key) { c in
                            Button {
                                if c.key != task.boardColumn { onMoveColumn(c.key) }
                            } label: {
                                if c.key == task.boardColumn {
                                    Label(c.label, systemImage: "checkmark")
                                } else {
                                    Text(c.label)
                                }
                            }
                        }
                    } label: {
                        Text(currentColumnLabel)
                            .font(.system(size: 9, weight: .semibold))
                            .foregroundColor(appState.themeText.opacity(0.8))
                            .tracking(0.3)
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .background(appState.themeText.opacity(0.08))
                            .cornerRadius(8)
                    }
                    .menuStyle(.borderlessButton)
                    .menuIndicator(.hidden)
                    .fixedSize()

                    if let initial = assigneeInitial, let name = assigneeDisplay {
                        Circle()
                            .fill(appState.themeAccent.opacity(0.18))
                            .frame(width: 14, height: 14)
                            .overlay(
                                Text(initial)
                                    .font(.system(size: 8, weight: .semibold))
                                    .foregroundColor(appState.themeAccent)
                            )
                        Text(name)
                            .font(.system(size: 10))
                            .foregroundColor(.secondary)
                            .lineLimit(1)
                            .truncationMode(.tail)
                    }

                    if let due = task.dueDate, !due.isEmpty {
                        Image(systemName: "calendar")
                            .font(.system(size: 9))
                            .foregroundColor(.secondary)
                        Text(due.prefix(10))
                            .font(.system(size: 10))
                            .foregroundColor(.secondary)
                    }
                }

                // Template + element tags on their own row so a crowded status
                // row never squeezes them into a vertical one-letter-per-line
                // strip (and never pushes the assignee off the card edge).
                if KanbanTemplate.from(category: task.category) != nil
                    || (elementName ?? task.elementName) != nil {
                    HStack(spacing: 5) {
                        if let tpl = KanbanTemplate.from(category: task.category) {
                            HStack(spacing: 2) {
                                Image(systemName: tpl.icon).font(.system(size: 7))
                                Text(tpl.displayName).font(.system(size: 8, weight: .semibold))
                                    .lineLimit(1)
                            }
                            .fixedSize(horizontal: true, vertical: false)
                            .foregroundColor(tpl.color)
                            .padding(.horizontal, 4)
                            .padding(.vertical, 1)
                            .background(tpl.color.opacity(0.15))
                            .cornerRadius(3)
                        }
                        if let elName = elementName ?? task.elementName {
                            HStack(spacing: 2) {
                                Image(systemName: "square.stack.3d.up.fill").font(.system(size: 7))
                                Text(elName).font(.system(size: 8, weight: .medium))
                                    .lineLimit(1)
                            }
                            .fixedSize(horizontal: true, vertical: false)
                            .foregroundColor(appState.themeAccent)
                            .padding(.horizontal, 4)
                            .padding(.vertical, 1)
                            .background(appState.themeAccent.opacity(0.12))
                            .cornerRadius(3)
                        }
                    }
                }

                if let total = task.subtaskTotal, total > 0 {
                    let done = task.subtaskDone ?? 0
                    let frac = CGFloat(done) / CGFloat(total)
                    let complete = done >= total
                    HStack(spacing: 5) {
                        Image(systemName: complete ? "checkmark.circle.fill" : "checklist")
                            .font(.system(size: 8))
                            .foregroundColor(complete ? .matcha500 : .secondary)
                        ZStack(alignment: .leading) {
                            Capsule().fill(appState.themeText.opacity(0.12))
                                .frame(width: 54, height: 3)
                            Capsule().fill(complete ? Color.matcha500 : appState.themeAccent)
                                .frame(width: 54 * frac, height: 3)
                        }
                        Text("\(done)/\(total)")
                            .font(.system(size: 9, weight: .medium))
                            .foregroundColor(.secondary)
                    }
                }

                timestampLine

                if !attachments.isEmpty {
                    attachmentStrip
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 8)
            .padding(.bottom, 8)
            .padding(.top, 4)
        }
        .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
        .elevatedCard(cornerRadius: 8)
        .onTapGesture(perform: onTap)
    }

    /// Header background tint by inactivity age. Clear when fresh / done.
    private var headerTint: Color {
        switch task.aging {
        case .none: return .clear
        case .warn: return .orange.opacity(0.18)
        case .overdue: return .red.opacity(0.18)
        }
    }

    /// "Added <date> at <time> · Moved <relative>" in Pacific time. The exact
    /// creation time makes wait-duration legible. Moved only shows once the
    /// card has crossed columns at least once (lastMovedAt != nil).
    @ViewBuilder
    private var timestampLine: some View {
        if let added = PacificDateFormatter.dateTime(task.createdAt) {
            HStack(spacing: 3) {
                Text("Added \(added)")
                if let moved = PacificDateFormatter.relative(task.lastMovedAt) {
                    Text("· Moved \(moved)")
                }
            }
            .font(.system(size: 9))
            .foregroundColor(.secondary)
        }
    }

    @ViewBuilder
    private var attachmentStrip: some View {
        if imageAttachments.isEmpty {
            HStack(spacing: 4) {
                Image(systemName: "paperclip")
                    .font(.system(size: 9))
                    .foregroundColor(.secondary)
                Text("\(attachments.count)")
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
            }
        } else {
            HStack(spacing: 4) {
                ForEach(imageAttachments.prefix(3)) { f in
                    AsyncImage(url: URL(string: f.storageUrl)) { phase in
                        switch phase {
                        case .success(let img):
                            img.resizable().aspectRatio(contentMode: .fill)
                        default:
                            Rectangle().fill(Color.white.opacity(0.08))
                        }
                    }
                    .frame(width: 24, height: 24)
                    .clipShape(RoundedRectangle(cornerRadius: 3))
                }
                let extras = (imageAttachments.count - 3) + nonImageCount
                if extras > 0 {
                    Text("+\(extras)")
                        .font(.system(size: 9, weight: .semibold))
                        .foregroundColor(.secondary)
                        .padding(.horizontal, 4)
                        .padding(.vertical, 2)
                        .background(Color.white.opacity(0.08))
                        .cornerRadius(3)
                }
            }
        }
    }
}
