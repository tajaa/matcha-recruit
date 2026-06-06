import SwiftUI

// MARK: - Activity graph (collaboration branching diagram)

/// Which view the ticket sheet is showing: the default sections, or the
/// activity graph.
enum ViewerMode { case list, graph }

/// Fixed geometry for the graph gutter. All constants — no GeometryReader, so
/// `laneX` is safe to call from a `Shape.path(in:)`.
enum GraphGeom {
    static let rowH: CGFloat = 52
    static let avatar: CGFloat = 30
    static let laneSpacing: CGFloat = 40
    static let laneInset: CGFloat = 24

    /// The history event types that earn a node — "key actions only".
    /// `column_change` IS a node (a reviewer's whole contribution can be moves —
    /// dropping them erased that person from the graph), but `graphModel`
    /// coalesces consecutive same-actor moves into one net transition and drops
    /// no-op churn, so the board shuffling doesn't drown out everything else.
    static let nodeEvents: Set<String> = [
        "created", "activity", "column_change", "assignee_change",
        "round_started", "subtask_added", "subtask_completed", "review_rejected",
        "subtask_rejected", "review_approved",
    ]

    static func laneX(_ i: Int) -> CGFloat { laneInset + CGFloat(i) * laneSpacing }

    /// Gutter width grows with lane count but is capped so the action card keeps
    /// a comfortable width on the graph sheet's wider layout.
    static func gutterW(laneCount: Int) -> CGFloat {
        min(280, laneInset + laneSpacing * CGFloat(max(1, laneCount - 1)) + avatar / 2 + 10)
    }
}

/// One collaborator column in the graph.
struct GraphLane: Identifiable {
    let id: String          // actorUserId, or "system"
    let name: String
    let avatarUrl: String?
    let color: Color
    let isSystem: Bool
}

/// One action placed in its actor's lane.
struct GraphNode: Identifiable {
    let id: String          // event.id
    let laneIndex: Int
    let color: Color
    let laneKey: String
    let event: MWTaskHistoryEntry
    let isSystem: Bool
    /// Where the ticket sat on the board at this node's time. `moved == true`
    /// when the column differs from the previous node's, so the badge can read
    /// as a transition ("Todo → In Progress") instead of a static location.
    let columnLabel: String?
    let columnFromLabel: String?
}

/// The curved "handoff" into this node: from the previous node's lane at the
/// top of the row down to this node's center. Vertical tangents give the
/// git-network look; degenerates to a straight vertical when the lane is
/// unchanged (same person acting again).
private struct IncomingEdge: Shape {
    let fromX: CGFloat
    let toX: CGFloat
    func path(in r: CGRect) -> Path {
        var p = Path()
        let start = CGPoint(x: fromX, y: r.minY)
        let end = CGPoint(x: toX, y: r.midY)
        p.move(to: start)
        if abs(fromX - toX) < 0.5 {
            p.addLine(to: end)
        } else {
            let span = end.y - start.y
            p.addCurve(
                to: end,
                control1: CGPoint(x: fromX, y: start.y + span * 0.55),
                control2: CGPoint(x: toX, y: start.y + span * 0.45)
            )
        }
        return p
    }
}

/// The vertical stub from this node's center down to the row bottom — the lane
/// "continuing" toward the next row. Meets the next row's IncomingEdge at the
/// row boundary, so the spine reads as continuous.
private struct ExitStub: Shape {
    let x: CGFloat
    func path(in r: CGRect) -> Path {
        var p = Path()
        p.move(to: CGPoint(x: x, y: r.midY))
        p.addLine(to: CGPoint(x: x, y: r.maxY))
        return p
    }
}

/// One row of the graph: gutter (lane spines + handoff edge + avatar node) on
/// the left, a compact chat-style action card on the right. Per-row Shapes mean
/// each row owns its own height + edge geometry, so nothing can desync.
struct GraphRow: View {
    let node: GraphNode
    let prevLaneIndex: Int?
    let prevColor: Color?
    let laneCount: Int
    let gutterW: CGFloat
    let roundLabel: Int?
    let showExit: Bool
    /// The most recent real action — "you are here" on the timeline.
    var isCurrent: Bool = false
    /// Live board status for the current node ("CHANGES REQUESTED", "IN REVIEW",
    /// …) so the newest row reads like the ticket header, not just a log line.
    var currentStatusLabel: String? = nil
    var currentStatusTint: Color = .mwInkStrong

    @Environment(AppState.self) private var appState
    /// Tap a node → read its full (untruncated) note/text in a popover, so the
    /// graph stays usable for people who live in the node view.
    @State private var showFull = false

    private var laneX: CGFloat { GraphGeom.laneX(node.laneIndex) }
    private var isComment: Bool { node.event.eventType == "activity" }

    /// Full, untruncated text for the tap-to-read popover.
    private var fullBody: String {
        if isComment {
            return (node.event.metadata?["body"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        }
        return EventRow.describe(node.event)
    }
    /// Nodes whose label routinely truncates — worth a "click to read" cue.
    private var hasReadableBody: Bool {
        isComment || ["review_rejected", "round_started", "subtask_rejected"].contains(node.event.eventType)
    }

    /// Actor name surfaced on the card so each row says WHO acted, not only the
    /// (sometimes terse) action label. Nil for system events.
    private var actorCaption: String? {
        if node.isSystem { return nil }
        let n = node.event.actorName ?? ""
        return n.isEmpty ? nil : n
    }

    private var cardIcon: String {
        isComment ? "text.bubble" : EventRow.icon(for: node.event.eventType)
    }
    private var cardTint: Color {
        isComment ? .mwInkSoft : EventRow.tint(for: node.event.eventType)
    }
    private var who: String {
        node.event.actorName?.isEmpty == false ? node.event.actorName! : "Someone"
    }
    private var cardLabel: String {
        if isComment {
            let body = (node.event.metadata?["body"] ?? "")
                .replacingOccurrences(of: "\n", with: " ")
                .trimmingCharacters(in: .whitespacesAndNewlines)
            return body.isEmpty ? "\(who) commented" : "\(who): \(body)"
        }
        // Moves use the COALESCED net transition, not the raw last hop.
        if node.event.eventType == "column_change", let to = node.columnLabel {
            if let from = node.columnFromLabel { return "\(who) moved \(from) → \(to)" }
            return "\(who) moved to \(to)"
        }
        return EventRow.describe(node.event)
    }

    var body: some View {
        HStack(alignment: .top, spacing: 0) {
            gutter
            card
        }
        .frame(minHeight: GraphGeom.rowH, alignment: .top)
    }

    private var gutter: some View {
        ZStack(alignment: .topLeading) {
            // Faint full-height spine for every lane — anchors the columns.
            ForEach(0..<laneCount, id: \.self) { i in
                Rectangle()
                    .fill(Color.secondary.opacity(0.10))
                    .frame(width: 1.5, height: GraphGeom.rowH)
                    .offset(x: GraphGeom.laneX(i) - 0.75, y: 0)
            }
            // Incoming handoff, colored by the handing-off actor.
            if let prevLaneIndex {
                IncomingEdge(fromX: GraphGeom.laneX(prevLaneIndex), toX: laneX)
                    .stroke((prevColor ?? .secondary).opacity(0.85),
                            style: StrokeStyle(lineWidth: 2, lineCap: .round))
                    .frame(width: gutterW, height: GraphGeom.rowH)
            }
            // This lane continuing downward, colored by this actor.
            if showExit {
                ExitStub(x: laneX)
                    .stroke(node.color.opacity(0.85),
                            style: StrokeStyle(lineWidth: 2, lineCap: .round))
                    .frame(width: gutterW, height: GraphGeom.rowH)
            }
            // The node itself.
            nodeAvatar
                .frame(width: GraphGeom.avatar, height: GraphGeom.avatar)
                .offset(x: laneX - GraphGeom.avatar / 2,
                        y: GraphGeom.rowH / 2 - GraphGeom.avatar / 2)
        }
        .frame(width: gutterW, height: GraphGeom.rowH, alignment: .topLeading)
    }

    @ViewBuilder
    private var nodeAvatar: some View {
        if node.isSystem {
            Circle()
                .fill(Color.zinc800)
                .overlay(
                    Image(systemName: EventRow.icon(for: node.event.eventType))
                        .font(.system(size: 10))
                        .foregroundColor(.secondary)
                )
                .overlay(Circle().stroke(ringColor, lineWidth: ringWidth))
        } else {
            ChannelAvatarView(
                senderId: node.laneKey,
                payloadURL: node.event.actorAvatarUrl,
                name: node.event.actorName ?? "",
                size: GraphGeom.avatar
            )
            .overlay(Circle().stroke(ringColor, lineWidth: ringWidth))
        }
    }

    private var ringColor: Color {
        isCurrent ? .mwInkStrong : (node.isSystem ? .appBackground : node.color.opacity(0.9))
    }
    private var ringWidth: CGFloat { isCurrent ? 2.5 : 1.5 }

    private var card: some View {
        VStack(alignment: .leading, spacing: 3) {
            // Current node reads like the ticket header: "● YOU ARE HERE · CHANGES
            // REQUESTED" — the live board status, not just the last logged action.
            if isCurrent {
                HStack(spacing: 5) {
                    Circle().fill(currentStatusTint).frame(width: 5, height: 5)
                    Text("YOU ARE HERE")
                        .font(.system(size: 8, weight: .bold))
                        .tracking(0.6)
                        .foregroundColor(currentStatusTint)
                    if let s = currentStatusLabel {
                        Text(s)
                            .font(.system(size: 8, weight: .bold))
                            .tracking(0.4)
                            .foregroundColor(currentStatusTint)
                            .padding(.horizontal, 5)
                            .padding(.vertical, 1)
                            .background(currentStatusTint.opacity(0.18))
                            .cornerRadius(3)
                    }
                    Spacer(minLength: 0)
                }
            }
            HStack(spacing: 6) {
                Image(systemName: cardIcon)
                    .font(.system(size: 11))
                    .foregroundColor(cardTint)
                    .frame(width: 14)
                Text(cardLabel)
                    .font(.system(size: 12))
                    .foregroundColor(appState.themeText.opacity(0.9))
                    .lineLimit(1)
                    .truncationMode(.tail)
                Spacer(minLength: 0)
                if hasReadableBody {
                    Image(systemName: "chevron.right")
                        .font(.system(size: 8, weight: .semibold))
                        .foregroundColor(.secondary)
                }
                if let roundLabel {
                    Text("R\(roundLabel)")
                        .font(.system(size: 8, weight: .semibold))
                        .foregroundColor(.mwInkSoft)
                        .padding(.horizontal, 4)
                        .padding(.vertical, 1)
                        .background(Color.mwInkSoft.opacity(0.12))
                        .cornerRadius(3)
                }
            }
            HStack(spacing: 6) {
                if let who = actorCaption {
                    Text(who)
                        .font(.system(size: 9, weight: .semibold))
                        .foregroundColor(appState.themeText.opacity(0.7))
                        .lineLimit(1)
                    Text("·").font(.system(size: 9)).foregroundColor(.secondary)
                }
                Text(PacificDateFormatter.absolute(node.event.createdAt) ?? node.event.createdAt)
                    .font(.system(size: 9))
                    .foregroundColor(.secondary)
                columnBadge
            }
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(isCurrent ? currentStatusTint.opacity(0.12) : appState.themeText.opacity(0.06))
        .overlay(
            isCurrent
                ? RoundedRectangle(cornerRadius: 6).strokeBorder(currentStatusTint.opacity(0.35), lineWidth: 1)
                : nil
        )
        .cornerRadius(6)
        .contentShape(Rectangle())
        .onTapGesture { showFull = true }
        .help(hasReadableBody ? "Click to read the full note" : "")
        .popover(isPresented: $showFull, arrowEdge: .leading) {
            VStack(alignment: .leading, spacing: 8) {
                HStack(spacing: 6) {
                    Text(who).font(.system(size: 11, weight: .semibold)).foregroundColor(appState.themeText)
                    Text(PacificDateFormatter.absolute(node.event.createdAt) ?? node.event.createdAt)
                        .font(.system(size: 9)).foregroundColor(.secondary)
                    Spacer(minLength: 0)
                }
                ScrollView {
                    Text(fullBody.isEmpty ? cardLabel : fullBody)
                        .font(.system(size: 12))
                        .foregroundColor(appState.themeText.opacity(0.9))
                        .textSelection(.enabled)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .frame(maxHeight: 320)
            }
            .padding(12).frame(width: 320)
            .background(appState.themeCard)
        }
        .padding(.vertical, 3)
    }

    /// Where the ticket sat on the board at this node's time. A plain muted pill
    /// for "still here", or an accented "From → To" transition pill the moment
    /// it moved — so kanban moves stay visible without each being its own node.
    @ViewBuilder
    private var columnBadge: some View {
        // Move nodes already say "moved X → Y" in the label — don't double up.
        if node.event.eventType != "column_change", let to = node.columnLabel {
            if let from = node.columnFromLabel {
                HStack(spacing: 3) {
                    Text(from)
                    Image(systemName: "arrow.right").font(.system(size: 7, weight: .bold))
                    Text(to).fontWeight(.semibold)
                }
                .font(.system(size: 8, weight: .medium))
                .foregroundColor(.mwInkStrong)
                .padding(.horizontal, 5)
                .padding(.vertical, 1)
                .background(Color.mwInkStrong.opacity(0.10))
                .cornerRadius(3)
            } else {
                Text(to)
                    .font(.system(size: 8, weight: .medium))
                    .foregroundColor(.secondary)
                    .padding(.horizontal, 5)
                    .padding(.vertical, 1)
                    .background(Color.secondary.opacity(0.12))
                    .cornerRadius(3)
            }
        }
    }
}

/// A still-open checklist item, drawn as a hollow "future" node in the
/// assignee's lane — the graph showing remaining work, not just history. The
/// dashed ring + dashed lead-in read as "to do" against the solid, done past,
/// so the spine literally continues into what hasn't happened yet.
struct GhostRow: View {
    let title: String
    let assignee: String?
    let laneIndex: Int
    let color: Color
    let laneCount: Int
    let gutterW: CGFloat
    /// Lane of the row above so the dashed lead-in meets the spine above. Nil for
    /// the topmost ghost (nothing precedes it now that ghosts render at the top).
    let connectFromLane: Int?
    /// Ghosts sit above the newest real node, so each one's spine continues DOWN
    /// to the row below (another ghost, then the current node).
    var showExit: Bool = true

    private var laneX: CGFloat { GraphGeom.laneX(laneIndex) }

    var body: some View {
        HStack(alignment: .top, spacing: 0) {
            gutter
            card
        }
        .frame(minHeight: GraphGeom.rowH, alignment: .top)
    }

    private var gutter: some View {
        ZStack(alignment: .topLeading) {
            ForEach(0..<laneCount, id: \.self) { i in
                Rectangle()
                    .fill(Color.secondary.opacity(0.10))
                    .frame(width: 1.5, height: GraphGeom.rowH)
                    .offset(x: GraphGeom.laneX(i) - 0.75, y: 0)
            }
            if let connectFromLane {
                IncomingEdge(fromX: GraphGeom.laneX(connectFromLane), toX: laneX)
                    .stroke(color.opacity(0.5),
                            style: StrokeStyle(lineWidth: 1.5, lineCap: .round, dash: [3, 3]))
                    .frame(width: gutterW, height: GraphGeom.rowH)
            }
            // Dashed spine continuing down toward the node below.
            if showExit {
                ExitStub(x: laneX)
                    .stroke(color.opacity(0.5),
                            style: StrokeStyle(lineWidth: 1.5, lineCap: .round, dash: [3, 3]))
                    .frame(width: gutterW, height: GraphGeom.rowH)
            }
            Circle()
                .fill(Color.appBackground)
                .overlay(
                    Circle().strokeBorder(
                        color.opacity(0.7),
                        style: StrokeStyle(lineWidth: 1.5, dash: [2.5, 2.5]))
                )
                .frame(width: GraphGeom.avatar, height: GraphGeom.avatar)
                .offset(x: laneX - GraphGeom.avatar / 2,
                        y: GraphGeom.rowH / 2 - GraphGeom.avatar / 2)
        }
        .frame(width: gutterW, height: GraphGeom.rowH, alignment: .topLeading)
    }

    private var card: some View {
        HStack(spacing: 6) {
            Image(systemName: "square.dashed")
                .font(.system(size: 11))
                .foregroundColor(.secondary)
                .frame(width: 14)
            Text(title)
                .font(.system(size: 12))
                .foregroundColor(.secondary)
                .lineLimit(1)
                .truncationMode(.tail)
            Spacer(minLength: 0)
            if let assignee {
                Text(assignee)
                    .font(.system(size: 8, weight: .medium))
                    .foregroundColor(.secondary)
                    .padding(.horizontal, 5)
                    .padding(.vertical, 1)
                    .background(Color.secondary.opacity(0.12))
                    .cornerRadius(3)
            }
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
        .frame(maxWidth: .infinity, alignment: .leading)
        .overlay(
            RoundedRectangle(cornerRadius: 6)
                .strokeBorder(Color.secondary.opacity(0.18),
                              style: StrokeStyle(lineWidth: 1, dash: [4, 3]))
        )
        .padding(.vertical, 3)
    }
}
