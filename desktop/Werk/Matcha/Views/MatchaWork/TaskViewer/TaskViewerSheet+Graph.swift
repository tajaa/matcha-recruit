import SwiftUI

// MARK: - Activity graph (collaboration branching diagram)

extension TaskViewerSheet {
    /// One toggle pill for the header List/Graph control.
    @ViewBuilder
    func modeButton(_ mode: ViewerMode, icon: String) -> some View {
        Button { viewMode = mode } label: {
            Image(systemName: icon)
                .font(.system(size: 10))
                .foregroundColor(viewMode == mode ? .matcha500 : .secondary)
                .frame(width: 22, height: 18)
                .background(viewMode == mode ? Color.matcha500.opacity(0.18) : Color.clear)
                .cornerRadius(3)
        }
        .buttonStyle(.plain)
        .help(mode == .list ? "List view" : "Activity graph — collaboration as a branching diagram")
    }

    /// Lanes + nodes for the graph, computed once from the loaded history.
    /// Pure (no formatters / side effects); never reference this inside a
    /// GeometryReader body (see repo memory `werk-geometryreader-resize-perf`).
    /// Lane index = first-appearance order of each actor; null-actor (system)
    /// events collapse into a single `system` lane.
    var graphModel: (nodes: [GraphNode], lanes: [GraphLane]) {
        let sorted = history
            .filter { GraphGeom.nodeEvents.contains($0.eventType) }
            .sorted { $0.createdAt < $1.createdAt }
        // Coalesce: a run of back-to-back moves by the SAME actor collapses to
        // its last move, so "Todo → In Progress → Review" by one person is one
        // node, not three. (Can't synthesize a merged entry — the model is
        // all-`let` with a custom decoder — so we keep the run's final move and
        // recover the net origin from `columnAt(previous node)` below.)
        var coalesced: [MWTaskHistoryEntry] = []
        for e in sorted {
            if e.eventType == "column_change",
               let last = coalesced.last,
               last.eventType == "column_change",
               last.actorUserId == e.actorUserId {
                coalesced[coalesced.count - 1] = e
            } else {
                coalesced.append(e)
            }
        }
        // Column-at-time timeline, reconstructed from the FULL history (initial
        // column from `created`, then every move) so each node knows where the
        // ticket sat — and move nodes can render their net transition.
        let moves = history
            .filter { $0.eventType == "column_change" || $0.eventType == "created" }
            .sorted { $0.createdAt < $1.createdAt }
        func columnAt(_ ts: String) -> String? {
            var col: String?
            for m in moves where m.createdAt <= ts {
                if let to = m.toValue { col = to }
            }
            return col
        }
        var laneKeys: [String] = []
        var laneInfo: [String: GraphLane] = [:]
        var nodes: [GraphNode] = []
        var lastCol: String?
        var seenAny = false
        for e in coalesced {
            let cur = columnAt(e.createdAt)
            let from = seenAny ? lastCol : nil
            let moved = cur != nil && from != nil && cur != from
            // Drop no-op churn: a move that nets back to where it started (e.g.
            // Todo → In Progress → Todo) carries no signal.
            if e.eventType == "column_change", !moved { continue }
            seenAny = true
            if cur != nil { lastCol = cur }

            let isSystem = (e.actorUserId == nil)
            let key = e.actorUserId ?? "system"
            let color = e.actorUserId.map(UserColor.forUserId) ?? .secondary
            if !laneKeys.contains(key) {
                laneKeys.append(key)
                laneInfo[key] = GraphLane(
                    id: key,
                    name: isSystem ? "System"
                        : (e.actorName?.isEmpty == false ? e.actorName! : "Someone"),
                    avatarUrl: e.actorAvatarUrl,
                    color: color,
                    isSystem: isSystem
                )
            }
            let lane = laneKeys.firstIndex(of: key) ?? 0
            nodes.append(GraphNode(
                id: e.id, laneIndex: lane, color: color,
                laneKey: key, event: e, isSystem: isSystem,
                columnLabel: cur.map(EventRow.columnLabel),
                columnFromLabel: moved ? from.map(EventRow.columnLabel) : nil
            ))
        }
        return (nodes, laneKeys.compactMap { laneInfo[$0] })
    }

    /// System events render a neutral symbol bubble; real actors render their
    /// avatar. Shared by the legend and (re-implemented for sizing) the nodes.
    @ViewBuilder
    func laneAvatar(_ lane: GraphLane, size: CGFloat) -> some View {
        if lane.isSystem {
            Circle()
                .fill(Color.zinc800)
                .frame(width: size, height: size)
                .overlay(
                    Image(systemName: "gearshape.fill")
                        .font(.system(size: size * 0.5))
                        .foregroundColor(.secondary)
                )
        } else {
            ChannelAvatarView(
                senderId: lane.id,
                payloadURL: lane.avatarUrl,
                name: lane.name,
                size: size
            )
        }
    }

    /// Color-coded who's-who legend above the graph (avatars are tight in the
    /// gutter, so names live here rather than under each lane).
    func graphLegend(_ lanes: [GraphLane]) -> some View {
        HStack(spacing: 12) {
            ForEach(lanes) { lane in
                HStack(spacing: 6) {
                    laneAvatar(lane, size: 22)
                        .overlay(Circle().stroke(lane.color.opacity(0.9), lineWidth: 1.5))
                    Text(lane.name)
                        .font(.system(size: 11, weight: .medium))
                        .foregroundColor(.white.opacity(0.8))
                        .lineLimit(1)
                }
            }
            Spacer(minLength: 0)
        }
    }

    func graphRoundBand(round: Int) -> some View {
        HStack(spacing: 6) {
            Text("ROUND \(round)")
                .font(.system(size: 8, weight: .bold))
                .tracking(0.5)
                .foregroundColor(.matcha500)
                .padding(.horizontal, 6)
                .padding(.vertical, 2)
                .background(Color.matcha500.opacity(0.15))
                .cornerRadius(3)
            Rectangle()
                .fill(Color.matcha500.opacity(0.2))
                .frame(height: 1)
        }
        .padding(.top, 8)
        .padding(.bottom, 4)
    }

    /// Done from any of the signals the board uses.
    var taskIsDone: Bool {
        task.status == "done" || task.boardColumn == "done" || task.completedAt != nil
    }

    /// "You are here" — current state + the implied next action, derived purely
    /// from the LIVE task/subtask state (no history needed). This is what turns
    /// the graph from a backward audit into "where we stand + what's next".
    var graphStatusCard: some View {
        let open = subtasks.filter { !$0.isDone }
        let assignee = assigneeName ?? "Unassigned"
        let col = task.boardColumn
        let titles = open.prefix(2).map(\.title).joined(separator: ", ")
        let more = open.count > 2 ? " +\(open.count - 2) more" : ""
        let n = open.count
        let items = "\(n) item\(n == 1 ? "" : "s")"

        let headline: String
        let sub: String
        let tint: Color
        let icon: String
        if taskIsDone {
            headline = "Complete"
            sub = "Nothing left — this ticket is done."
            tint = .matcha500
            icon = "checkmark.seal.fill"
        } else {
            switch col {
            case "review":
                headline = "In review"
                sub = "Waiting on \(assignee) to sign off."
                tint = .blue
                icon = "eye.fill"
            case "changes_requested":
                headline = "Changes requested"
                sub = open.isEmpty
                    ? "\(assignee) to rework and resubmit."
                    : "\(assignee) to fix \(items): \(titles)\(more)"
                tint = .orange
                icon = "arrow.uturn.backward"
            default:
                headline = EventRow.columnLabel(col)
                sub = open.isEmpty
                    ? "\(assignee) · checklist clear — ready to move forward."
                    : "\(assignee) · \(items) left: \(titles)\(more)"
                tint = .matcha500
                icon = "location.fill"
            }
        }

        return HStack(alignment: .top, spacing: 10) {
            Image(systemName: icon)
                .font(.system(size: 15))
                .foregroundColor(tint)
                .frame(width: 18)
            VStack(alignment: .leading, spacing: 3) {
                Text("WHERE WE STAND")
                    .font(.system(size: 8, weight: .bold))
                    .tracking(0.6)
                    .foregroundColor(tint.opacity(0.8))
                HStack(spacing: 6) {
                    Text(headline)
                        .font(.system(size: 13, weight: .bold))
                        .foregroundColor(tint)
                    if currentRound > 1 {
                        Text("ROUND \(currentRound)")
                            .font(.system(size: 8, weight: .bold))
                            .tracking(0.4)
                            .foregroundColor(.matcha500)
                            .padding(.horizontal, 5)
                            .padding(.vertical, 1)
                            .background(Color.matcha500.opacity(0.15))
                            .cornerRadius(3)
                    }
                }
                Text(sub)
                    .font(.system(size: 11))
                    .foregroundColor(.white.opacity(0.85))
                    .fixedSize(horizontal: false, vertical: true)
            }
            Spacer(minLength: 0)
        }
        .padding(11)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(tint.opacity(0.12))
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .strokeBorder(tint.opacity(0.3), lineWidth: 1)
        )
        .cornerRadius(8)
    }

    var activityGraphSection: some View {
        let model = graphModel
        let nodes = model.nodes
        let lanes = model.lanes
        let laneCount = max(1, lanes.count)
        let gutterW = GraphGeom.gutterW(laneCount: laneCount)
        let openSubtasks = taskIsDone ? [] : subtasks.filter { !$0.isDone }
        let assigneeLane = lanes.firstIndex(where: { $0.id == task.assignedTo })
        let ghostLane = assigneeLane ?? nodes.last?.laneIndex ?? 0
        let ghostColor = task.assignedTo.map(UserColor.forUserId) ?? .secondary
        return VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 6) {
                Image(systemName: "point.3.connected.trianglepath.dotted")
                    .font(.system(size: 10))
                Text("ACTIVITY GRAPH")
                    .font(.system(size: 9, weight: .semibold))
                    .tracking(0.5)
                Spacer()
                if nodes.count > 1 {
                    Text("\(nodes.count) actions · \(lanes.count) \(lanes.count == 1 ? "person" : "people")")
                        .font(.system(size: 9))
                        .foregroundColor(.secondary)
                }
            }
            .foregroundColor(.matcha500)

            // Where we stand + what's next — always first, even before history loads.
            graphStatusCard

            if nodes.isEmpty {
                Text(loadingHistory ? "Loading activity…" : "No activity yet")
                    .font(.system(size: 12))
                    .foregroundColor(.secondary)
                    .padding(.vertical, 10)
            } else {
                graphLegend(lanes)
                VStack(spacing: 0) {
                    ForEach(Array(nodes.enumerated()), id: \.element.id) { idx, node in
                        let prev = idx > 0 ? nodes[idx - 1] : nil
                        let r = roundIndex(forCreatedAt: node.event.createdAt)
                        let prevR = prev.map { roundIndex(forCreatedAt: $0.event.createdAt) }
                        if currentRound > 1, prev == nil || prevR != r {
                            graphRoundBand(round: r)
                        }
                        GraphRow(
                            node: node,
                            prevLaneIndex: prev?.laneIndex,
                            prevColor: prev?.color,
                            laneCount: laneCount,
                            gutterW: gutterW,
                            roundLabel: currentRound > 1 ? r : nil,
                            // Spine continues into the ghost (pending) rows too.
                            showExit: idx < nodes.count - 1 || !openSubtasks.isEmpty,
                            isCurrent: idx == nodes.count - 1
                        )
                    }
                    // Remaining work as hollow "future" nodes in the assignee's lane.
                    ForEach(Array(openSubtasks.enumerated()), id: \.element.id) { gi, st in
                        GhostRow(
                            title: st.title,
                            assignee: assigneeName,
                            laneIndex: ghostLane,
                            color: ghostColor,
                            laneCount: laneCount,
                            gutterW: gutterW,
                            connectFromLane: gi == 0 ? nodes.last?.laneIndex : ghostLane
                        )
                    }
                }
            }
        }
        .padding(.vertical, 4)
    }
}
