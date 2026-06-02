import SwiftUI

// MARK: - Activity graph (collaboration branching diagram)

/// Which view the ticket sheet is showing: the default sections, or the
/// activity graph.
enum ViewerMode { case list, graph }

/// Fixed geometry for the graph gutter. All constants — no GeometryReader, so
/// `laneX` is safe to call from a `Shape.path(in:)`.
enum GraphGeom {
    static let rowH: CGFloat = 44
    static let avatar: CGFloat = 22
    static let laneSpacing: CGFloat = 28
    static let laneInset: CGFloat = 18

    /// The history event types that earn a node — "key actions only".
    static let nodeEvents: Set<String> = [
        "created", "activity", "column_change", "assignee_change",
        "round_started", "subtask_added", "subtask_completed", "review_rejected",
    ]

    static func laneX(_ i: Int) -> CGFloat { laneInset + CGFloat(i) * laneSpacing }

    /// Gutter width grows with lane count but is capped so the action card keeps
    /// ≥ ~330pt on the sheet's fixed 600pt width.
    static func gutterW(laneCount: Int) -> CGFloat {
        min(220, laneInset + laneSpacing * CGFloat(max(1, laneCount - 1)) + avatar / 2 + 8)
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

    private var laneX: CGFloat { GraphGeom.laneX(node.laneIndex) }
    private var isComment: Bool { node.event.eventType == "activity" }

    private var cardIcon: String {
        isComment ? "text.bubble" : EventRow.icon(for: node.event.eventType)
    }
    private var cardTint: Color {
        isComment ? .blue : EventRow.tint(for: node.event.eventType)
    }
    private var cardLabel: String {
        guard isComment else { return EventRow.describe(node.event) }
        let body = (node.event.metadata?["body"] ?? "")
            .replacingOccurrences(of: "\n", with: " ")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        let who = node.event.actorName?.isEmpty == false ? node.event.actorName! : "Someone"
        return body.isEmpty ? "\(who) commented" : "\(who): \(body)"
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
                .overlay(Circle().stroke(Color.appBackground, lineWidth: 1.5))
        } else {
            ChannelAvatarView(
                senderId: node.laneKey,
                payloadURL: node.event.actorAvatarUrl,
                name: node.event.actorName ?? "",
                size: GraphGeom.avatar
            )
            .overlay(Circle().stroke(node.color.opacity(0.9), lineWidth: 1.5))
        }
    }

    private var card: some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack(spacing: 6) {
                Image(systemName: cardIcon)
                    .font(.system(size: 11))
                    .foregroundColor(cardTint)
                    .frame(width: 14)
                Text(cardLabel)
                    .font(.system(size: 12))
                    .foregroundColor(.white.opacity(0.9))
                    .lineLimit(1)
                    .truncationMode(.tail)
                Spacer(minLength: 0)
                if let roundLabel {
                    Text("R\(roundLabel)")
                        .font(.system(size: 8, weight: .semibold))
                        .foregroundColor(.matcha500)
                        .padding(.horizontal, 4)
                        .padding(.vertical, 1)
                        .background(Color.matcha500.opacity(0.15))
                        .cornerRadius(3)
                }
            }
            Text(PacificDateFormatter.absolute(node.event.createdAt) ?? node.event.createdAt)
                .font(.system(size: 9))
                .foregroundColor(.secondary)
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.zinc800.opacity(0.45))
        .cornerRadius(6)
        .padding(.vertical, 3)
    }
}
