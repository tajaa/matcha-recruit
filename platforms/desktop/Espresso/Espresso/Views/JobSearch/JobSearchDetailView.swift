import SwiftUI
import AppKit

/// A job search, as Tasks shows it (job searches are tasks): its ranked jobs
/// in the middle, and the open job (pay with its source, how to approach it,
/// drafted answers and letter) on the right. Tasks owns the list, starting a
/// search and deleting one.
struct JobSearchDetailView: View {
    @Environment(AppState.self) private var appState
    let searchId: String
    /// A job to open (a chat card, a link to it).
    var focusLeadId: String? = nil
    @State private var vm = JobSearchViewModel()
    @State private var showWeights = false
    /// Next steps folded to one line (everywhere, once someone knows them).
    @AppStorage("jobs.nextSteps.collapsed") private var stepsCollapsed = false
    /// How wide the list side is, to pick the full table or the compact list.
    @State private var contentWidth: CGFloat = 1000

    /// What the compact list needs: rank, a truncated role, Pay, Fit, Status.
    nonisolated static let minContentWidth: CGFloat = 440
    /// What the full table needs at its ideal column widths.
    nonisolated static let fullTableWidth: CGFloat = 660

    /// The full table sizes its columns once, when it appears; after that only
    /// its last column gives way, so a pane dragged wider would push Fit and
    /// Status off screen. Beside a job, or when narrow, the list is a plain
    /// one whose rows lay out at whatever width they get.
    nonisolated static func usesCompactList(leadOpen: Bool, width: CGFloat) -> Bool {
        leadOpen || width < fullTableWidth
    }

    var body: some View {
        GeometryReader { geo in
            HStack(spacing: 0) {
                content
                    .frame(minWidth: Self.minContentWidth, maxWidth: .infinity, maxHeight: .infinity)
                    .onGeometryChange(for: CGFloat.self) { $0.size.width } action: { contentWidth = $0 }
                if vm.selectedLeadId != nil {
                    ResizableTrailingPane(storageKey: "jobs.leadPaneWidth", defaultWidth: 440,
                                          maxWidth: geo.size.width - Self.minContentWidth) {
                        JobLeadDetailView(vm: vm, onClose: { Task { await vm.selectLead(nil) } })
                    }
                }
            }
        }
        .featureGuideOnFirstVisit(.jobSearch)
        .task(id: searchId) {
            await vm.open(searchId, leadId: focusLeadId)
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(5))
                guard !Task.isCancelled else { break }
                await vm.poll()
            }
        }
        .onChange(of: focusLeadId) { _, leadId in
            if let leadId { Task { await vm.selectLead(leadId) } }
        }
        .onChange(of: vm.planFeature) { _, feature in
            if let feature { appState.presentPaywall(for: feature); vm.planFeature = nil }
        }
    }

    // MARK: Content

    @ViewBuilder
    private var content: some View {
        if let detail = vm.detail {
            VStack(spacing: 0) {
                header(detail.search)
                Divider().opacity(0.2)
                if let error = vm.errorMessage { errorBanner(error) }
                if !detail.search.isLive && !detail.leads.isEmpty {
                    nextSteps(detail)
                    Divider().opacity(0.2)
                }
                let wider = JobSearchViewModel.widerCount(detail)
                if wider > 0 {
                    widerBar(wider)
                    Divider().opacity(0.2)
                }
                filters(detail)
                leadsTable
            }
        } else if let error = vm.errorMessage {
            VStack(spacing: 10) {
                Image(systemName: "exclamationmark.triangle")
                    .font(.system(size: 30))
                    .foregroundColor(appState.themeTextSecondary.opacity(0.7))
                Text("Couldn't load this job search")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(appState.themeText)
                Text(error)
                    .font(.system(size: 12))
                    .foregroundColor(appState.themeTextSecondary)
                    .multilineTextAlignment(.center)
                    .frame(maxWidth: 460)
                Button("Try again") { Task { await vm.open(searchId, leadId: nil) } }
                    .buttonStyle(.borderedProminent)
                    .tint(appState.themeAccent)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else {
            ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }

    /// The person's own state first, then where its first message is.
    nonisolated static func statusText(_ lead: JobLeadSummary) -> String {
        if lead.isIrrelevant { return "Screened out" }
        if lead.isBelowFloor && lead.userState == "new" { return "Weaker fit" }
        if lead.userState == "applied" { return "Applied" }
        if lead.emailSentAt != nil { return "Emailed" }
        if lead.emailWaiting { return "In drafts" }
        return lead.userState == "new" ? "" : lead.userState.capitalized
    }

    // MARK: Next steps

    /// What to do with a finished search, in order, and how far along it is.
    private func nextSteps(_ detail: JobSearchDetail) -> some View {
        let progress = JobSearchViewModel.progress(detail.leads)
        return VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                Text("NEXT STEPS")
                    .font(.system(size: 10, weight: .semibold))
                    .tracking(0.6)
                    .foregroundColor(appState.themeTextSecondary)
                if let line = progress.line {
                    Text(line).font(.system(size: 11)).foregroundColor(appState.themeAccent)
                }
                Spacer()
                Button(stepsCollapsed ? "Show" : "Hide") { stepsCollapsed.toggle() }
                    .buttonStyle(.plain)
                    .font(.system(size: 11))
                    .foregroundColor(appState.themeTextSecondary)
            }
            if !stepsCollapsed {
                step(1, progress.drafted > 0
                     ? "Read your best matches. \(progress.drafted) have a drafted approach: how to get in, a first message, answers and a cover letter."
                     : "Read your best matches, and draft an approach for any you like from its page.",
                     action: progress.drafted > 0 && vm.filter != .drafted ? ("Show them", { vm.filter = .drafted }) : nil)
                step(2, "Open one you want and click Draft email. It goes to your Gmail drafts, to edit and send from Email.",
                     action: progress.emailsWaiting > 0 ? ("Open drafts", { appState.openEmailDrafts() }) : nil)
                step(3, "Apply through the posting, then mark the job Applied so you can keep track.", action: nil)
            }
        }
        .padding(.horizontal, 18).padding(.vertical, 10)
        .background(appState.themeAccent.opacity(0.04))
    }

    /// The first pass shows the 4/5 and 5/5 jobs; this offers the 3/5 ones.
    private func widerBar(_ count: Int) -> some View {
        HStack(spacing: 8) {
            Image(systemName: "line.3.horizontal.decrease.circle")
                .foregroundColor(appState.themeTextSecondary)
            Text("Showing your strongest matches (4/5 or better). "
                 + (count == 1 ? "1 more job scored 3/5." : "\(count) more jobs scored 3/5."))
                .font(.system(size: 12))
                .foregroundColor(appState.themeText)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 8)
            Button("Show \(count) more at 3/5") { Task { await vm.widen() } }
                .buttonStyle(.bordered)
                .controlSize(.small)
                .disabled(vm.busy)
        }
        .padding(.horizontal, 18).padding(.vertical, 8)
    }

    private func step(_ n: Int, _ text: String, action: (String, () -> Void)?) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            Text("\(n)")
                .font(.system(size: 10, weight: .bold))
                .foregroundColor(.white)
                .frame(width: 16, height: 16)
                .background(Circle().fill(appState.themeAccent))
            Text(text)
                .font(.system(size: 12))
                .foregroundColor(appState.themeText)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 8)
            if let action {
                Button(action.0, action: action.1)
                    .buttonStyle(.bordered)
                    .controlSize(.small)
            }
        }
    }

    private func header(_ search: JobSearchSummary) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .firstTextBaseline, spacing: 10) {
                Text(search.displayTitle)
                    .font(.system(size: 18, weight: .bold))
                    .foregroundColor(appState.themeText)
                    .lineLimit(1)
                Spacer(minLength: 8)
                Button { showWeights.toggle() } label: {
                    Label("What matters", systemImage: "slider.horizontal.3").font(.system(size: 11))
                }
                .buttonStyle(.plain)
                .foregroundColor(appState.themeTextSecondary)
                .disabled(search.isLive || vm.busy)
                .popover(isPresented: $showWeights) {
                    WeightsPopover(initial: search.weights) { weights in
                        showWeights = false
                        Task { await vm.rerank(weights) }
                    }
                    .environment(appState)
                }
                if search.isLive {
                    Button("Cancel") { Task { await vm.cancel() } }
                        .buttonStyle(.bordered)
                        .disabled(vm.busy)
                }
            }
            if !search.ask.isEmpty && search.ask != search.displayTitle {
                Text(search.ask)
                    .font(.system(size: 11))
                    .foregroundColor(appState.themeTextSecondary)
                    .lineLimit(2)
            }
            PhaseStepper(status: search.status)
            if let note = search.progress.note, !note.isEmpty {
                HStack(spacing: 6) {
                    if search.isLive { ProgressView().controlSize(.mini) }
                    Text(note)
                        .font(.system(size: 11))
                        .foregroundColor(search.status == "failed" ? .orange : appState.themeTextSecondary)
                }
            }
        }
        .padding(.horizontal, 18).padding(.vertical, 14)
    }

    /// One row when it fits; beside an open job, the checkbox and count drop
    /// to a second row, and narrower still the filter becomes a menu.
    private func filters(_ detail: JobSearchDetail) -> some View {
        let screened = Toggle("Show weaker matches", isOn: $vm.showIrrelevant)
            .toggleStyle(.checkbox)
            .font(.system(size: 11))
            .fixedSize()
        let count = Text("\(vm.visibleLeads.count) of \(detail.leads.count)")
            .font(.system(size: 10))
            .foregroundColor(appState.themeTextSecondary)
            .fixedSize()
        return ViewThatFits(in: .horizontal) {
            HStack(spacing: 10) {
                filterPicker.pickerStyle(.segmented).fixedSize()
                screened
                Spacer(minLength: 8)
                count
            }
            VStack(alignment: .leading, spacing: 6) {
                filterPicker.pickerStyle(.segmented).fixedSize()
                HStack { screened; Spacer(minLength: 8); count }
            }
            HStack(spacing: 10) {
                filterPicker.pickerStyle(.menu).fixedSize()
                screened
                Spacer(minLength: 8)
                count
            }
        }
        .padding(.horizontal, 18).padding(.vertical, 8)
    }

    private var filterPicker: some View {
        Picker("", selection: $vm.filter) {
            ForEach(JobSearchViewModel.Filter.allCases) { Text($0.rawValue).tag($0) }
        }
        .labelsHidden()
    }

    private var leadSelection: Binding<String?> {
        Binding(get: { vm.selectedLeadId }, set: { id in Task { await vm.selectLead(id) } })
    }

    @ViewBuilder
    private var leadsTable: some View {
        if Self.usesCompactList(leadOpen: vm.selectedLeadId != nil, width: contentWidth) {
            // Where it is moves under the company; Fit and Status (In drafts,
            // Emailed) keep fixed columns, and the role truncates instead.
            VStack(spacing: 0) {
                compactRow(rank: Text("#"), role: Text("Role"), pay: Text("Pay"),
                           fit: Text("Fit"), status: Text("Status"))
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundColor(appState.themeTextSecondary)
                    .padding(.horizontal, 18).padding(.vertical, 5)
                Divider().opacity(0.2)
                List(vm.visibleLeads, selection: leadSelection) { lead in
                    compactRow(
                        rank: Text(lead.rank.map(String.init) ?? "")
                            .font(.system(size: 11, design: .monospaced))
                            .foregroundColor(appState.themeTextSecondary),
                        role: roleCell(lead, withLocation: true),
                        pay: payCell(lead),
                        fit: fitCell(lead),
                        status: statusCell(lead)
                    )
                    .padding(.vertical, 3)
                }
                .listStyle(.inset(alternatesRowBackgrounds: false))
                .scrollContentBackground(.hidden)
            }
        } else {
            Table(vm.visibleLeads, selection: leadSelection) {
                TableColumn("#") { lead in
                    Text(lead.rank.map(String.init) ?? "")
                        .font(.system(size: 11, design: .monospaced))
                        .foregroundColor(appState.themeTextSecondary)
                }
                .width(24)
                // Ideal widths that fit at `fullTableWidth`; wider, the
                // table spreads the extra across them when it appears.
                TableColumn("Role") { roleCell($0, withLocation: false) }
                    .width(min: 160, ideal: 180)
                TableColumn("Location") { lead in
                    HStack(spacing: 4) {
                        Text(lead.location).lineLimit(1)
                        if Self.showsRemoteBadge(lead) {
                            Text("Remote").font(.system(size: 9, weight: .semibold))
                                .padding(.horizontal, 4).padding(.vertical, 1)
                                .background(Capsule().fill(appState.themeText.opacity(0.08)))
                        }
                    }
                    .font(.system(size: 11))
                }
                .width(min: 90, ideal: 100)
                TableColumn("Pay") { payCell($0) }
                    .width(min: 120, ideal: 130)
                TableColumn("Fit") { fitCell($0) }
                    .width(34)
                TableColumn("Status") { statusCell($0) }
                    .width(min: 64, ideal: 72)
            }
            .tableStyle(.inset(alternatesRowBackgrounds: false))
            .scrollContentBackground(.hidden)
        }
    }

    /// One compact row (or its header): the role takes what's left.
    private func compactRow(rank: some View, role: some View, pay: some View,
                            fit: some View, status: some View) -> some View {
        HStack(spacing: 10) {
            rank.frame(width: 20, alignment: .trailing)
            role.frame(maxWidth: .infinity, alignment: .leading)
            pay.frame(width: 128, alignment: .leading)
            fit.frame(width: 28, alignment: .leading)
            status.frame(width: 62, alignment: .leading)
        }
    }

    private func roleCell(_ lead: JobLeadSummary, withLocation: Bool) -> some View {
        HStack(spacing: 6) {
            VStack(alignment: .leading, spacing: 1) {
                Text(lead.title).font(.system(size: 12, weight: .semibold)).lineLimit(1)
                Text(withLocation ? Self.companyLine(lead) : lead.company)
                    .font(.system(size: 11))
                    .foregroundColor(appState.themeTextSecondary)
                    .lineLimit(1)
            }
            Spacer(minLength: 0)
            if lead.isDrafting {
                ProgressView().controlSize(.mini).help("Drafting the approach")
            } else if lead.approachStatus == "done" {
                Image(systemName: "text.badge.checkmark")
                    .font(.system(size: 10))
                    .foregroundColor(appState.themeAccent)
                    .help("Approach drafted")
            }
        }
    }

    private func payCell(_ lead: JobLeadSummary) -> some View {
        VStack(alignment: .leading, spacing: 1) {
            Text(lead.compLine).font(.system(size: 11, weight: .medium)).lineLimit(1)
            Text(JobSearchViewModel.compBadge(lead.compStatus))
                .font(.system(size: 9, weight: .semibold))
                .foregroundColor(lead.compStatus == "posted" ? .green : appState.themeTextSecondary)
        }
        .help(lead.flags.contains("below_floor") ? "Below your minimum base" : "")
    }

    private func fitCell(_ lead: JobLeadSummary) -> some View {
        Text(JobSearchViewModel.fitText(lead.fitScore))
            .font(.system(size: 11, design: .monospaced))
    }

    private func statusCell(_ lead: JobLeadSummary) -> some View {
        Text(Self.statusText(lead))
            .font(.system(size: 11))
            .foregroundColor(lead.emailWaiting ? appState.themeAccent : appState.themeTextSecondary)
            .lineLimit(1)
    }

    nonisolated static func showsRemoteBadge(_ lead: JobLeadSummary) -> Bool {
        lead.remote == true && !lead.location.localizedCaseInsensitiveContains("remote")
    }

    /// "Flex · New York, NY · Remote": the company, then where, for the compact table.
    nonisolated static func companyLine(_ lead: JobLeadSummary) -> String {
        var parts = [lead.company]
        if !lead.location.isEmpty { parts.append(lead.location) }
        if showsRemoteBadge(lead) { parts.append("Remote") }
        return parts.filter { !$0.isEmpty }.joined(separator: " · ")
    }

    // MARK: Pieces

    private func errorBanner(_ text: String) -> some View {
        HStack(spacing: 6) {
            Image(systemName: "exclamationmark.triangle.fill").font(.system(size: 10))
            Text(text).font(.system(size: 11)).lineLimit(2)
            Spacer()
            Button { vm.errorMessage = nil } label: {
                Image(systemName: "xmark").font(.system(size: 9, weight: .bold))
            }
            .buttonStyle(.plain)
        }
        .foregroundColor(.orange)
        .padding(.horizontal, 18).padding(.vertical, 6)
        .background(Color.orange.opacity(0.08))
    }
}

/// Plan → Search → Screen → Read pay → Draft approaches → Done.
private struct PhaseStepper: View {
    @Environment(AppState.self) private var appState
    let status: String

    var body: some View {
        let current = JobSearchPhase.from(status: status)
        // Narrow (beside a wide job pane): dots, and only the current step named.
        ViewThatFits(in: .horizontal) {
            steps(current, allLabels: true)
            steps(current, allLabels: false)
        }
    }

    private func steps(_ current: JobSearchPhase?, allLabels: Bool) -> some View {
        HStack(spacing: 6) {
            ForEach(JobSearchPhase.allCases) { phase in
                let reached = (current?.rawValue ?? -1) >= phase.rawValue
                let active = current == phase && JobSearchStatus.isLive(status)
                HStack(spacing: 4) {
                    Circle()
                        .fill(reached ? appState.themeAccent : appState.themeText.opacity(0.15))
                        .frame(width: 6, height: 6)
                    if allLabels || current == phase {
                        Text(phase.label)
                            .font(.system(size: 10, weight: active ? .semibold : .regular))
                            .foregroundColor(reached ? appState.themeText : appState.themeTextSecondary)
                            .fixedSize()
                    }
                }
                if phase != .done {
                    Rectangle().fill(appState.themeText.opacity(0.12)).frame(width: allLabels ? 12 : 8, height: 1)
                }
            }
            if current == nil {
                Text(JobSearchStatus.label(status))
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundColor(.orange)
            }
        }
    }
}

/// Re-rank with new weights. Free: no search is spent.
private struct WeightsPopover: View {
    @Environment(AppState.self) private var appState
    @State private var weights: JobSearchWeights
    let onApply: (JobSearchWeights) -> Void

    init(initial: JobSearchWeights, onApply: @escaping (JobSearchWeights) -> Void) {
        _weights = State(initialValue: initial)
        self.onApply = onApply
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("What matters most").font(.system(size: 13, weight: .semibold))
            WeightSliders(weights: $weights)
            Text("Jobs that don't post pay are ranked after those that do; unposted pay is never counted as zero.")
                .font(.system(size: 10))
                .foregroundColor(appState.themeTextSecondary)
                .fixedSize(horizontal: false, vertical: true)
            HStack {
                Button("Reset") { weights = .standard }
                Spacer()
                Button("Re-rank") { onApply(weights) }
                    .buttonStyle(.borderedProminent)
                    .tint(appState.themeAccent)
                    .disabled(!weights.anyAboveZero)
            }
        }
        .padding(16)
        .frame(width: 300)
    }
}

/// The four sliders, shared by the new-search sheet and the re-rank popover.
struct WeightSliders: View {
    @Binding var weights: JobSearchWeights

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            row("Base salary", $weights.base)
            row("Bonus", $weights.bonus)
            row("Equity", $weights.equity)
            row("Fit with what I asked", $weights.fit)
        }
    }

    private func row(_ label: String, _ value: Binding<Double>) -> some View {
        HStack(spacing: 8) {
            Text(label).font(.system(size: 11)).frame(width: 130, alignment: .leading)
            Slider(value: value, in: 0...1)
            Text("\(Int((value.wrappedValue * 100).rounded()))")
                .font(.system(size: 10, design: .monospaced))
                .frame(width: 26, alignment: .trailing)
        }
    }
}
