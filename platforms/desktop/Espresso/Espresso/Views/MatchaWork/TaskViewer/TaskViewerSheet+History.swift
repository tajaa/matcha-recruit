import SwiftUI

// MARK: - Background context: collapsibles + the rounds/audit History feed
//
// Split out of TaskViewerSheet+Sections.swift. Everything here is one click away
// by design — supporting detail that must not crowd the directive hero.

extension TaskViewerSheet {

    // MARK: - Generic disclosure

    var contributorDisplayName: String {
        let name = task.createdByName?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return name.isEmpty ? "Contributor" : name
    }

    /// Generic disclosure row mirroring `historyToggle` so supporting context
    /// keeps the brief and AI summary collapsible without nesting scroll panels.
    @ViewBuilder
    func collapsibleSection<Content: View>(
        title: String, badge: String? = nil,
        isOpen: Binding<Bool>, onFirstOpen: (() -> Void)? = nil,
        @ViewBuilder content: () -> Content
    ) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Button {
                if !isOpen.wrappedValue { onFirstOpen?() }
                withAnimation(.easeInOut(duration: 0.18)) { isOpen.wrappedValue.toggle() }
            } label: {
                HStack(spacing: 8) {
                    TicketSectionHeading(title: title, detail: badge)
                    Image(systemName: isOpen.wrappedValue ? "chevron.up" : "chevron.down")
                        .font(.ticket(size: 9)).foregroundStyle(.secondary)
                }
                .padding(.vertical, 4)
                .contentShape(Rectangle())
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
            collapsibleSection(
                title: "Contributor brief",
                badge: contributorDisplayName,
                isOpen: $showDescription
            ) {
                TicketBriefText(text: desc).foregroundColor(appState.themeText)
            }
        }
    }

    /// AI catch-up summary behind a ▸ toggle. Only appears once generated (the
    /// sparkle button fills it and auto-expands). Closed on a later reopen.
    @ViewBuilder
    var aiSummaryCollapsible: some View {
        if let summary = viewModel.taskSummaries[task.id], !summary.isEmpty {
            collapsibleSection(title: "AI summary", isOpen: $showSummary) {
                Text(summary)
                    .font(.ticket(size: 12)).foregroundColor(appState.themeText.opacity(0.9))
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
            .font(.ticket(size: 10))
            .foregroundColor(.mwInkStrong)
            .padding(.horizontal, 5)
            .padding(.vertical, 1)
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
                    .font(.ticket(size: 10))
                    .foregroundColor(.secondary)
                Text("History")
                    .font(.ticket(size: 10))
                    .foregroundColor(.secondary)

                if rounds.count > 1 {
                    Text("\(rounds.count) rounds")
                        .font(.ticket(size: 10))
                        .foregroundColor(.secondary)
                        .padding(.horizontal, 5)
                        .padding(.vertical, 1)
                        .background(appState.themeText.opacity(0.08))
                        .cornerRadius(4)
                }
                Spacer()
                Text("Show")
                    .font(.ticket(size: 10))
                    .foregroundColor(.mwInkStrong)
                Image(systemName: "chevron.down")
                    .font(.ticket(size: 10))
                    .foregroundColor(.mwInkStrong)
            }
            .padding(.vertical, 8)
            .frame(maxWidth: .infinity)
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
                    autoPRBotUserId: viewModel.autoPRBotUserId,
                    onPreview: { previewFile = $0 }
                )
            }
        }
    }

    private var historySectionHeader: some View {
        HStack(spacing: 6) {
            Image(systemName: "clock.arrow.circlepath")
                .font(.ticket(size: 10))
                .foregroundColor(.secondary)
            Text("History")
                .font(.ticket(size: 10))
                .foregroundColor(.secondary)

            if !rounds.isEmpty {
                Text("\(rounds.count) round\(rounds.count == 1 ? "" : "s")")
                    .font(.ticket(size: 10))
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
                    .font(.ticket(size: 10))
                    .foregroundColor(.secondary)
            }
            .buttonStyle(.plain)
            .help("Collapse history")
            Button {
                showingNewRoundSheet = true
            } label: {
                HStack(spacing: 4) {
                    Image(systemName: "plus.circle.fill")
                        .font(.ticket(size: 10))
                    Text("Start Next Round")
                        .font(.ticket(size: 10))
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
