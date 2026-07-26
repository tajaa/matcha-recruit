import SwiftUI

// MARK: - Background context: collapsibles + the rounds/audit History feed
//
// Split out of TaskViewerSheet+Sections.swift. Everything here is one click away
// by design — supporting detail that must not crowd the directive hero.

extension TaskViewerSheet {

    // MARK: - Generic disclosure

    /// Generic disclosure row mirroring `historyToggle` so supporting context
    /// (description, AI summary) sits one click away instead of crowding the
    /// directive. Closed by default.
    @ViewBuilder
    func collapsibleSection<Content: View>(
        icon: String, title: String, badge: String? = nil, tint: Color = .secondary,
        isOpen: Binding<Bool>, onFirstOpen: (() -> Void)? = nil,
        @ViewBuilder content: () -> Content
    ) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Button {
                if !isOpen.wrappedValue { onFirstOpen?() }
                withAnimation(.easeInOut(duration: 0.18)) { isOpen.wrappedValue.toggle() }
            } label: {
                if appState.isGraphite {
                    HStack(spacing: 8) {
                        Text(isOpen.wrappedValue ? "[-]" : "[+]")
                            .font(.system(size: 10, design: .monospaced))
                            .foregroundColor(appState.themeTextSecondary)
                        asciiRule(badge.map { "\(title) · \($0)" } ?? title)
                    }
                    .padding(.vertical, 7).frame(maxWidth: .infinity).contentShape(Rectangle())
                } else {
                    HStack(spacing: 6) {
                        Image(systemName: icon).font(.system(size: 10)).foregroundColor(tint)
                        Text(title).font(.system(size: 9, weight: .semibold)).foregroundColor(tint).tracking(0.5)
                        if let badge {
                            Text(badge).font(.system(size: 9)).foregroundColor(.secondary)
                                .padding(.horizontal, 5).padding(.vertical, 1)
                                .background(appState.themeText.opacity(0.08)).cornerRadius(4)
                        }
                        Spacer()
                        Image(systemName: isOpen.wrappedValue ? "chevron.up" : "chevron.down")
                            .font(.system(size: 9, weight: .semibold)).foregroundColor(.secondary)
                    }
                    .padding(.vertical, 8).padding(.horizontal, 10).frame(maxWidth: .infinity)
                    .background(appState.themeText.opacity(0.07)).cornerRadius(6).contentShape(Rectangle())
                }
            }
            .buttonStyle(.plain)
            if isOpen.wrappedValue { content() }
        }
    }

    /// Description behind a ▸ toggle (unless it's already the hero on a fresh
    /// ticket).
    @ViewBuilder
    var descriptionCollapsible: some View {
        if !descriptionIsHero,
           let desc = task.description?.trimmingCharacters(in: .whitespacesAndNewlines), !desc.isEmpty {
            collapsibleSection(icon: "doc.text", title: "DESCRIPTION", isOpen: $showDescription) {
                ScrollView {
                    Text(desc)
                        .font(.system(size: 13)).foregroundColor(appState.themeText.opacity(0.85))
                        .frame(maxWidth: .infinity, alignment: .leading).textSelection(.enabled)
                }
                .frame(maxHeight: 220).padding(10)
                .background(appState.themeText.opacity(0.07)).cornerRadius(6)
            }
        }
    }

    /// AI catch-up summary behind a ▸ toggle. Only appears once generated (the
    /// sparkle button fills it and auto-expands). Closed on a later reopen.
    @ViewBuilder
    var aiSummaryCollapsible: some View {
        if let summary = viewModel.taskSummaries[task.id], !summary.isEmpty {
            collapsibleSection(icon: "sparkles", title: "AI SUMMARY", tint: .mwInkStrong, isOpen: $showSummary) {
                Text(summary)
                    .font(.system(size: 12)).foregroundColor(appState.themeText.opacity(0.9))
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal, 2)
            }
        }
    }

    // MARK: - Round scope

    // (Former `currentRoundCard` removed — the latest-round detail now lives in
    // the collapsed History, which includes the current round.)

    /// Small "Round N" chip marking a foreground section as scoped to the live
    /// round, so it's explicit the body is showing the current round's work.
    var roundScopePill: some View {
        Text("Round \(currentRound)")
            .font(.system(size: 8, weight: .semibold))
            .foregroundColor(.mwInkStrong)
            .padding(.horizontal, 5)
            .padding(.vertical, 1)
            .background(Color.mwInkStrong.opacity(0.15))
            .cornerRadius(4)
    }

    // MARK: - History (rounds-grouped audit)

    /// Collapsed stand-in for the rounds + audit History feed (the background).
    /// History is already loaded on open for the Discussion thread, so tapping
    /// just reveals it; the lazy fetch stays as a safety net.
    var historyToggle: some View {
        Button {
            showHistory = true
            if !historyLoaded {
                Task { await loadHistory() }
            }
        } label: {
            HStack(spacing: 6) {
                Image(systemName: "clock.arrow.circlepath")
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
                Text("HISTORY")
                    .font(.system(size: 9, weight: .semibold))
                    .foregroundColor(.secondary)
                    .tracking(0.5)
                if rounds.count > 1 {
                    Text("\(rounds.count) rounds")
                        .font(.system(size: 9))
                        .foregroundColor(.secondary)
                        .padding(.horizontal, 5)
                        .padding(.vertical, 1)
                        .background(appState.themeText.opacity(0.08))
                        .cornerRadius(4)
                }
                Spacer()
                Text("Show")
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundColor(.mwInkStrong)
                Image(systemName: "chevron.down")
                    .font(.system(size: 9, weight: .semibold))
                    .foregroundColor(.mwInkStrong)
            }
            .padding(.vertical, 8)
            .padding(.horizontal, 10)
            .frame(maxWidth: .infinity)
            .background(appState.themeText.opacity(0.07))
            .cornerRadius(6)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    /// The background: structural rounds + audit trail. Collapsed by default
    /// (toggled via `historyToggle`). Prior rounds carry their fixed items and
    /// older attachments out of the foreground. Hosts "Start Next Round".
    @ViewBuilder
    var historySection: some View {
        VStack(alignment: .leading, spacing: 8) {
            historySectionHeader

            // Rounds rendered newest-first so the active round sits on top.
            // Within each round events stay chronological (oldest → newest).
            // `previousFixed` threads the prior round's completed subtask
            // titles forward so round N+1 shows "Fixed in Round N · …".
            // Show ALL rounds here (newest-first). The latest round used to be a
            // separate inline "LATEST UPDATE" card; the reorg folded it into this
            // collapsed History, so it must include the current round or the
            // round detail would show nowhere.
            let reversed = Array(rounds.reversed())
            ForEach(Array(reversed.enumerated()), id: \.element.id) { idx, round in
                // `reversed` is newest-first; the round AFTER this one in
                // chronological time is the previous element in `reversed`
                // (idx-1). For the latest round (idx 0) there's no "next."
                // The summary block belongs ON round N+1, so we look at
                // round N = reversed[idx+1] when rendering reversed[idx].
                let previousIndex = idx + 1
                let previousFixed: [String] = (previousIndex < reversed.count)
                    ? reversed[previousIndex].fixedSubtaskTitles
                    : []
                RoundView(
                    round: round,
                    previousFixed: round.index >= 2 ? previousFixed : [],
                    files: attachments,
                    onPreview: { previewFile = $0 }
                )
            }
        }
    }

    private var historySectionHeader: some View {
        HStack(spacing: 6) {
            Image(systemName: "clock.arrow.circlepath")
                .font(.system(size: 10))
                .foregroundColor(.secondary)
            Text("HISTORY")
                .font(.system(size: 9, weight: .semibold))
                .foregroundColor(.secondary)
                .tracking(0.5)
            if !rounds.isEmpty {
                Text("\(rounds.count) round\(rounds.count == 1 ? "" : "s")")
                    .font(.system(size: 9))
                    .foregroundColor(.secondary)
                    .padding(.horizontal, 5)
                    .padding(.vertical, 1)
                    .background(appState.themeText.opacity(0.08))
                    .cornerRadius(4)
            }
            if loadingHistory {
                ProgressView().controlSize(.small)
            }
            Spacer()
            Button { showHistory = false } label: {
                Image(systemName: "chevron.up")
                    .font(.system(size: 9, weight: .semibold))
                    .foregroundColor(.secondary)
            }
            .buttonStyle(.plain)
            .help("Collapse history")
            Button {
                showingNewRoundSheet = true
            } label: {
                HStack(spacing: 4) {
                    Image(systemName: "plus.circle.fill")
                        .font(.system(size: 10))
                    Text("Start Next Round")
                        .font(.system(size: 10, weight: .semibold))
                }
                .foregroundColor(.mwInkStrong)
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .background(Color.mwInkStrong.opacity(0.12))
                .cornerRadius(4)
            }
            .buttonStyle(.plain)
            .help("Open a new round with a suggested-fix subtask. Any collaborator can start one.")
        }
    }
}
