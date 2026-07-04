import SwiftUI

/// "History" tab — time-lapse replay of a project's kanban activity for one
/// week (Mon 12:00am–Sun 11:59:59pm Pacific). Week picker up top, the replay
/// board in the middle, and a scrubber + play/pause transport bar pinned
/// below.
struct WeeklyReplayView: View {
    @Environment(AppState.self) private var appState
    let viewModel: ProjectDetailViewModel
    @State private var replayVM: WeeklyReplayViewModel?

    var body: some View {
        VStack(spacing: 0) {
            weekPicker
            Divider().opacity(0.2)
            content
            Divider().opacity(0.2)
            transportBar
        }
        .task(id: viewModel.project?.id) {
            guard let pid = viewModel.project?.id else { return }
            if replayVM?.projectId != pid {
                replayVM = WeeklyReplayViewModel(projectId: pid)
            }
        }
    }

    private var weekPicker: some View {
        HStack {
            Button { replayVM?.previousWeek() } label: {
                Image(systemName: "chevron.left")
            }
            .buttonStyle(.plain)

            Text(replayVM?.weekLabel ?? "")
                .font(.system(size: 13, weight: .semibold))
                .frame(minWidth: 140)

            Button { replayVM?.nextWeek() } label: {
                Image(systemName: "chevron.right")
            }
            .buttonStyle(.plain)

            Spacer()

            if let moment = replayVM?.currentMomentLabel {
                Text(moment)
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
    }

    @ViewBuilder
    private var content: some View {
        if let vm = replayVM {
            if vm.isLoading {
                ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if let error = vm.loadError {
                Text(error)
                    .foregroundColor(.secondary)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if vm.eventCount == 0 && vm.currentState.isEmpty {
                Text("No activity this week.")
                    .foregroundColor(.secondary)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                ReplayBoardView(tasks: Array(vm.currentState.values))
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        } else {
            Color.clear
        }
    }

    private var transportBar: some View {
        HStack(spacing: 14) {
            Button {
                replayVM?.togglePlay()
            } label: {
                Image(systemName: (replayVM?.isPlaying ?? false) ? "pause.fill" : "play.fill")
                    .font(.system(size: 13))
            }
            .buttonStyle(.plain)
            .disabled((replayVM?.eventCount ?? 0) == 0)

            scrubber
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
    }

    /// Draggable playhead across the week — position maps linearly to the
    /// nearest event index (not to real elapsed time; events can cluster, and
    /// a simple index-based scrub is enough to "jump to any moment").
    private var scrubber: some View {
        GeometryReader { geo in
            let count = max(replayVM?.eventCount ?? 0, 1)
            let progress = CGFloat(replayVM?.scrubIndex ?? 0) / CGFloat(count)
            ZStack(alignment: .leading) {
                Capsule().fill(appState.themeText.opacity(0.12)).frame(height: 4)
                Capsule().fill(appState.themeAccent).frame(width: geo.size.width * progress, height: 4)
                Circle().fill(appState.themeAccent)
                    .frame(width: 12, height: 12)
                    .offset(x: geo.size.width * progress - 6)
            }
            .frame(maxHeight: .infinity)
            .contentShape(Rectangle())
            .gesture(
                DragGesture(minimumDistance: 0).onChanged { value in
                    guard let replayVM, replayVM.eventCount > 0 else { return }
                    replayVM.pause()
                    let pct = max(0, min(1, value.location.x / geo.size.width))
                    let index = Int((pct * CGFloat(replayVM.eventCount)).rounded())
                    replayVM.scrub(to: index)
                }
            )
        }
        .frame(height: 20)
    }
}
