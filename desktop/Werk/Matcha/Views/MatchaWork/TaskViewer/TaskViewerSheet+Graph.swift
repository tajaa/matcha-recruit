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
        var laneKeys: [String] = []
        var laneInfo: [String: GraphLane] = [:]
        var nodes: [GraphNode] = []
        for e in sorted {
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
                laneKey: key, event: e, isSystem: isSystem
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
                HStack(spacing: 5) {
                    laneAvatar(lane, size: 16)
                        .overlay(Circle().stroke(lane.color.opacity(0.9), lineWidth: 1.5))
                    Text(lane.name)
                        .font(.system(size: 9, weight: .medium))
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

    var activityGraphSection: some View {
        let model = graphModel
        let nodes = model.nodes
        let lanes = model.lanes
        let laneCount = max(1, lanes.count)
        let gutterW = GraphGeom.gutterW(laneCount: laneCount)
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
                            showExit: idx < nodes.count - 1
                        )
                    }
                }
            }
        }
        .padding(.vertical, 4)
    }
}
