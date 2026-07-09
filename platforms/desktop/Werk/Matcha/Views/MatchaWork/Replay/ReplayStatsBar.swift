import SwiftUI

/// "What happened this week" strip above the replay board. Counts come from the
/// events folded in so far, not the week's end-of-week totals, so they tick up
/// as the replay plays and read as a live scoreboard of the week.
///
/// Zero-valued tallies are omitted rather than shown as "0 deleted" — a quiet
/// week should look quiet, not like a form with empty fields.
struct ReplayStatsBar: View {
    @Environment(AppState.self) private var appState
    let stats: ReplayStats

    /// Contributors named before the rest collapse into a "+N" chip.
    private let maxNamed = 3

    var body: some View {
        HStack(spacing: 10) {
            if stats.isEmpty {
                Text("Nothing yet this week.")
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
            } else {
                tallies
            }
            Spacer()
            contributors
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 8)
        .animation(.easeOut(duration: 0.2), value: stats)
    }

    @ViewBuilder
    private var tallies: some View {
        pill("plus.circle", stats.created, "created")
        pill("arrow.left.arrow.right", stats.moved, "moved")
        pill("checkmark.circle", stats.completed, "finished", tint: .green)
        pill("arrow.uturn.backward", stats.sentBack, "sent back", tint: .orange)
        pill("trash", stats.deleted, "deleted")
        pill("checklist", stats.subtasksCompleted, "subtasks done")
    }

    @ViewBuilder
    private func pill(_ icon: String, _ count: Int, _ label: String, tint: Color? = nil) -> some View {
        if count > 0 {
            HStack(spacing: 4) {
                Image(systemName: icon)
                    .font(.system(size: 10, weight: .semibold))
                Text("\(count)")
                    .font(.system(size: 11, weight: .semibold))
                    // Roll the digits as the replay advances instead of
                    // hard-cutting them — the counter reads as accumulating.
                    .contentTransition(.numericText())
                Text(label)
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
            }
            .foregroundColor(tint ?? appState.themeText)
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(appState.themeText.opacity(0.06))
            .clipShape(Capsule())
        }
    }

    @ViewBuilder
    private var contributors: some View {
        if !stats.contributors.isEmpty {
            HStack(spacing: 6) {
                ForEach(stats.contributors.prefix(maxNamed)) { person in
                    HStack(spacing: 4) {
                        ChannelAvatarView(
                            senderId: person.id,
                            payloadURL: person.avatarUrl,
                            name: person.name,
                            size: 16
                        )
                        Text(person.name)
                            .font(.system(size: 11))
                            .foregroundColor(.secondary)
                            .lineLimit(1)
                    }
                }
                if stats.contributors.count > maxNamed {
                    Text("+\(stats.contributors.count - maxNamed)")
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundColor(.secondary)
                }
            }
        }
    }
}
