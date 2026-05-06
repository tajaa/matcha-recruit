import SwiftUI

/// Compact done/total progress indicator for a kanban task list.
/// Shows a 4px-tall rounded bar plus an "X / Y · NN%" label.
struct TaskProgressBar: View {
    let tasks: [MWProjectTask]
    var compact: Bool = false

    private var doneCount: Int {
        tasks.filter { $0.status == "completed" }.count
    }

    private var fraction: Double {
        guard !tasks.isEmpty else { return 0 }
        return Double(doneCount) / Double(tasks.count)
    }

    private var percentLabel: String {
        guard !tasks.isEmpty else { return "0%" }
        return "\(Int((fraction * 100).rounded()))%"
    }

    var body: some View {
        HStack(spacing: 8) {
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    RoundedRectangle(cornerRadius: 2)
                        .fill(Color.zinc800)
                    RoundedRectangle(cornerRadius: 2)
                        .fill(Color.matcha500)
                        .frame(width: max(0, geo.size.width * fraction))
                        .animation(.easeOut(duration: 0.25), value: fraction)
                }
            }
            .frame(height: 4)

            Text(tasks.isEmpty
                ? "0 tasks"
                : "\(doneCount) / \(tasks.count) · \(percentLabel)")
                .font(.system(size: compact ? 9 : 10, weight: .medium))
                .foregroundColor(.white.opacity(0.55))
                .fixedSize()
        }
    }
}
