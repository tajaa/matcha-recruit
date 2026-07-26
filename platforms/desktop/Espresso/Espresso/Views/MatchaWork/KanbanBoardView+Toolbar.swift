import SwiftUI

// MARK: - Board / Pipeline / List picker + the pipeline summary bar
//
// Split out of KanbanBoardView.swift. (The old `headerBar` went with it — it
// was `private` and no call site ever referenced it.)

extension KanbanBoardView {

    var boardPipelinePicker: some View {
        HStack(spacing: 0) {
            viewModeButton("Board", mode: .board, icon: "square.grid.2x2")
            // Pipeline only exists for collab projects; Board/List for all.
            if viewModel.project?.projectType == "collab" {
                viewModeButton("Pipeline", mode: .pipeline, icon: "dollarsign.circle")
            }
            listModeButton
            Spacer()
        }
        .padding(.horizontal, 12)
        .padding(.bottom, 4)
    }

    private func viewModeButton(_ label: String, mode: KanbanViewMode, icon: String) -> some View {
        modeChip(label, icon: icon, active: viewMode == mode && !showListView) {
            viewMode = mode
            showListView = false
        }
    }

    /// Linear layout of the same tickets — columns become sections with a
    /// Mine filter (KanbanListView).
    private var listModeButton: some View {
        modeChip("List", icon: "list.bullet", active: showListView) {
            showListView = true
        }
    }

    /// The three picker chips are identical but for their label, icon, active
    /// test and action — they were three near-copies of the same 16 lines.
    private func modeChip(_ label: String, icon: String, active: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 4) {
                Image(systemName: icon).font(.system(size: 10))
                Text(label).font(.system(size: 11, weight: .medium))
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(active ? appState.themeAccent.opacity(0.15) : Color.clear)
            .foregroundColor(active ? appState.themeAccent : .secondary)
            .cornerRadius(5)
        }
        .buttonStyle(.plain)
    }

    /// Sales-pipeline summary bar — open value, weighted forecast, won, count,
    /// win rate. Sits under the search/progress row; pipeline mode only.
    var pipelineSummaryBar: some View {
        let s = pipelineSummary
        return HStack(spacing: 14) {
            summaryStat("Open", formatDealValue(s.openValue), appState.themeText)
            summaryStat("Forecast", formatDealValue(s.weightedValue), appState.themeAccent)
            summaryStat("Won", formatDealValue(s.wonValue), .green)
            Divider().frame(height: 18)
            summaryStat("Open deals", "\(s.openCount)", appState.themeText.opacity(0.8))
            summaryStat("Win rate", "\(Int((s.winRate * 100).rounded()))%", .green)
            Spacer()
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
    }

    private func summaryStat(_ label: String, _ value: String, _ color: Color) -> some View {
        VStack(alignment: .leading, spacing: 1) {
            Text(value).font(.system(size: 13, weight: .semibold)).foregroundColor(color)
            Text(label.uppercased())
                .font(.system(size: 8, weight: .semibold))
                .foregroundColor(.secondary)
                .tracking(0.4)
        }
    }
}
