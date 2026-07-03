import SwiftUI

/// Renders one TaskRound as a self-contained sub-ticket card: header
/// (Round N · CURRENT · phase) + title (suggested fix) + optional
/// "Fixed in previous round" inheritance summary + this round's events.
/// Latest round is expanded and gets a phase-colored border; older
/// rounds collapse under DisclosureGroup so a thrashing ticket doesn't
/// bury the active sub-todo under audit-log noise.
struct RoundView: View {
    let round: TaskRound
    let previousFixed: [String]
    let files: [MWProjectFile]
    let onPreview: (MWProjectFile) -> Void

    @State private var isExpanded: Bool

    init(
        round: TaskRound,
        previousFixed: [String],
        files: [MWProjectFile],
        onPreview: @escaping (MWProjectFile) -> Void
    ) {
        self.round = round
        self.previousFixed = previousFixed
        self.files = files
        self.onPreview = onPreview
        self._isExpanded = State(initialValue: round.isLatest)
    }

    private var phaseLabel: String { round.phaseLabel(isLatest: round.isLatest) }
    private var phaseColor: Color { round.phaseColor(isLatest: round.isLatest) }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            DisclosureGroup(isExpanded: $isExpanded) {
                VStack(alignment: .leading, spacing: 8) {
                    // "Fixed in Round N-1" inheritance block. Only shown on
                    // rounds 2+, only when the prior round actually
                    // completed something. Gives the reader at-a-glance
                    // continuity: "this round picks up from these closed
                    // items."
                    if !previousFixed.isEmpty {
                        VStack(alignment: .leading, spacing: 3) {
                            Text("FIXED IN ROUND \(round.index - 1)")
                                .font(.system(size: 8, weight: .semibold))
                                .foregroundColor(.mwInkStrong)
                                .tracking(0.6)
                            ForEach(Array(previousFixed.enumerated()), id: \.offset) { _, title in
                                HStack(spacing: 6) {
                                    Image(systemName: "checkmark.circle.fill")
                                        .font(.system(size: 10))
                                        .foregroundColor(.mwInkStrong)
                                    Text(title)
                                        .font(.system(size: 11))
                                        .foregroundColor(.mwInk.opacity(0.85))
                                        .strikethrough()
                                        .lineLimit(2)
                                }
                            }
                        }
                        .padding(8)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(Color.mwInkStrong.opacity(0.08))
                        .cornerRadius(5)
                    }

                    // A busy round (many moves/notes/subtask events) makes the
                    // card runaway-tall. Cap it and scroll internally past a
                    // threshold; short rounds render inline with no scrollbar.
                    let eventsStack = VStack(alignment: .leading, spacing: 4) {
                        ForEach(round.events) { event in
                            EventRow(event: event, files: files, onPreview: onPreview)
                        }
                    }
                    if round.events.count > 8 {
                        ScrollView { eventsStack }
                            .frame(height: 340)
                    } else {
                        eventsStack
                    }
                }
                .padding(.top, 6)
                .padding(.leading, 4)
            } label: {
                VStack(alignment: .leading, spacing: 4) {
                    HStack(spacing: 6) {
                        if round.isLatest {
                            HStack(spacing: 3) {
                                Circle()
                                    .fill(phaseColor)
                                    .frame(width: 6, height: 6)
                                Text("CURRENT")
                                    .font(.system(size: 8, weight: .bold))
                                    .foregroundColor(phaseColor)
                                    .tracking(0.7)
                            }
                            .padding(.horizontal, 5)
                            .padding(.vertical, 2)
                            .background(phaseColor.opacity(0.18))
                            .cornerRadius(3)
                        }
                        Text("Round \(round.index)")
                            .font(.system(size: 11, weight: .semibold))
                            .foregroundColor(.mwInk.opacity(0.9))
                        Text("·")
                            .font(.system(size: 11))
                            .foregroundColor(.secondary)
                        Text(phaseLabel)
                            .font(.system(size: 9, weight: .semibold))
                            .foregroundColor(phaseColor)
                            .tracking(0.5)
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .background(phaseColor.opacity(0.15))
                            .cornerRadius(3)
                        Spacer()
                        Text("\(round.events.count) event\(round.events.count == 1 ? "" : "s")")
                            .font(.system(size: 9))
                            .foregroundColor(.secondary)
                    }
                    // Round title (the suggested fix) — prominent because
                    // each round is a modular sub-todo with its own scope.
                    Text(round.title)
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundColor(.mwInk)
                        .lineLimit(2)
                        .multilineTextAlignment(.leading)
                }
            }
            .accentColor(.secondary)
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(round.isLatest ? Color.mwInk.opacity(0.08) : Color.mwInk.opacity(0.04))
        .overlay(
            RoundedRectangle(cornerRadius: 6)
                .stroke(round.isLatest ? phaseColor.opacity(0.45) : Color.clear, lineWidth: 1.5)
        )
        .cornerRadius(6)
    }
}
