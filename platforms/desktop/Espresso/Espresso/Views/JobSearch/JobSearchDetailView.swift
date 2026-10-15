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

    var body: some View {
        HStack(spacing: 0) {
            content.frame(minWidth: 380, maxWidth: .infinity, maxHeight: .infinity)
            if vm.selectedLeadId != nil {
                Divider().opacity(0.2)
                JobLeadDetailView(vm: vm, onClose: { Task { await vm.selectLead(nil) } })
                    .frame(width: 440)
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

    private func filters(_ detail: JobSearchDetail) -> some View {
        HStack(spacing: 10) {
            Picker("", selection: $vm.filter) {
                ForEach(JobSearchViewModel.Filter.allCases) { Text($0.rawValue).tag($0) }
            }
            .pickerStyle(.segmented)
            .labelsHidden()
            .frame(maxWidth: 420)
            Toggle("Show screened out", isOn: $vm.showIrrelevant)
                .toggleStyle(.checkbox)
                .font(.system(size: 11))
            Spacer()
            Text("\(vm.visibleLeads.count) of \(detail.leads.count)")
                .font(.system(size: 10))
                .foregroundColor(appState.themeTextSecondary)
        }
        .padding(.horizontal, 18).padding(.vertical, 8)
    }

    private var leadsTable: some View {
        Table(vm.visibleLeads, selection: Binding(
            get: { vm.selectedLeadId },
            set: { id in Task { await vm.selectLead(id) } }
        )) {
            TableColumn("#") { lead in
                Text(lead.rank.map(String.init) ?? "")
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundColor(appState.themeTextSecondary)
            }
            .width(28)
            TableColumn("Role") { lead in
                HStack(spacing: 6) {
                    VStack(alignment: .leading, spacing: 1) {
                        Text(lead.title).font(.system(size: 12, weight: .semibold)).lineLimit(1)
                        Text(lead.company).font(.system(size: 11)).foregroundColor(appState.themeTextSecondary)
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
            .width(min: 180, ideal: 260)
            TableColumn("Location") { lead in
                HStack(spacing: 4) {
                    Text(lead.location).lineLimit(1)
                    if lead.remote == true && !lead.location.localizedCaseInsensitiveContains("remote") {
                        Text("Remote").font(.system(size: 9, weight: .semibold))
                            .padding(.horizontal, 4).padding(.vertical, 1)
                            .background(Capsule().fill(appState.themeText.opacity(0.08)))
                    }
                }
                .font(.system(size: 11))
            }
            .width(min: 100, ideal: 150)
            TableColumn("Pay") { lead in
                VStack(alignment: .leading, spacing: 1) {
                    Text(lead.compLine).font(.system(size: 11, weight: .medium)).lineLimit(1)
                    Text(JobSearchViewModel.compBadge(lead.compStatus))
                        .font(.system(size: 9, weight: .semibold))
                        .foregroundColor(lead.compStatus == "posted" ? .green : appState.themeTextSecondary)
                }
                .help(lead.flags.contains("below_floor") ? "Below your minimum base" : "")
            }
            .width(min: 140, ideal: 200)
            TableColumn("Fit") { lead in
                Text(JobSearchViewModel.fitText(lead.fitScore))
                    .font(.system(size: 11, design: .monospaced))
            }
            .width(40)
            TableColumn("Status") { lead in
                Text(lead.isIrrelevant ? "Screened out" : lead.userState == "new" ? "" : lead.userState.capitalized)
                    .font(.system(size: 11))
                    .foregroundColor(appState.themeTextSecondary)
            }
            .width(80)
        }
        .tableStyle(.inset(alternatesRowBackgrounds: false))
        .scrollContentBackground(.hidden)
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
        HStack(spacing: 6) {
            ForEach(JobSearchPhase.allCases) { phase in
                let reached = (current?.rawValue ?? -1) >= phase.rawValue
                let active = current == phase && JobSearchStatus.isLive(status)
                HStack(spacing: 4) {
                    Circle()
                        .fill(reached ? appState.themeAccent : appState.themeText.opacity(0.15))
                        .frame(width: 6, height: 6)
                    Text(phase.label)
                        .font(.system(size: 10, weight: active ? .semibold : .regular))
                        .foregroundColor(reached ? appState.themeText : appState.themeTextSecondary)
                }
                if phase != .done {
                    Rectangle().fill(appState.themeText.opacity(0.12)).frame(width: 12, height: 1)
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
