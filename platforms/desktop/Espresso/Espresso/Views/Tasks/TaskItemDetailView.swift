import SwiftUI
import AppKit

/// One finding: its photos and page, every fact with the words and page it
/// came from, an apartment building's homes to let one by one, why it fits
/// (or why it's hidden), the person's notes, and what to do with it.
struct TaskItemDetailView: View {
    @Environment(AppState.self) private var appState
    let vm: TasksViewModel
    let onClose: () -> Void
    @State private var notes = ""
    @State private var notesItemId: String?
    @State private var flow: TaskActionFlow?
    @State private var allHomes = false

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Spacer()
                Button(action: onClose) {
                    Image(systemName: "xmark").font(.system(size: 10, weight: .bold))
                }
                .buttonStyle(.plain)
                .foregroundColor(appState.themeTextSecondary)
                .help("Close")
            }
            .padding(.horizontal, 14).padding(.top, 10)
            if let item = vm.item {
                ScrollView {
                    VStack(alignment: .leading, spacing: 18) {
                        heading(item)
                        if !item.images.isEmpty { photos(item) }
                        doneSection(item)
                        facts(item)
                        homesSection(item)
                        fitSection(item)
                        notesSection(item)
                        actions(item)
                    }
                    .padding(.horizontal, 18).padding(.bottom, 24)
                }
                .onAppear { syncNotes(item) }
                .onChange(of: item.id) { _, _ in syncNotes(item) }
            } else {
                ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .background(appState.themeBg.opacity(0.4))
        .sheet(item: $flow) { flow in
            TaskActionSheet(flow: flow) { Task { await vm.reloadItem() } }
                .environment(appState)
        }
    }

    private func syncNotes(_ item: AgentTaskItem) {
        if notesItemId != item.id {
            notes = item.notes
            notesItemId = item.id
            allHomes = false
        }
    }

    private func heading(_ item: AgentTaskItem) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(item.title)
                .font(.system(size: 16, weight: .bold))
                .foregroundColor(appState.themeText)
                .fixedSize(horizontal: false, vertical: true)
            if !item.subtitle.isEmpty {
                Text(item.subtitle).font(.system(size: 12)).foregroundColor(appState.themeTextSecondary)
            }
            if let url = TasksViewModel.webURL(item.url) {
                Link(destination: url) {
                    Label(TasksViewModel.linkLabel(url), systemImage: "arrow.up.right.square")
                        .font(.system(size: 11))
                }
            }
            if let reason = item.hiddenReason {
                Text(reason).font(.system(size: 11, weight: .medium)).foregroundColor(.orange)
            }
            HStack(spacing: 6) {
                stateButton("Save", state: "saved", icon: "bookmark", item: item)
                stateButton("Choose", state: "chosen", icon: "checkmark.seal", item: item)
                stateButton("Dismiss", state: "dismissed", icon: "eye.slash", item: item)
            }
            .padding(.top, 2)
            if !item.actions.isEmpty { doRow(item) }
        }
    }

    /// What the finding can do in the world, as the server says: each opens
    /// a sheet that shows exactly what will happen before it does.
    private func doRow(_ item: AgentTaskItem) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 6) {
                ForEach(item.actions) { action in
                    Button {
                        if let taskId = vm.selectedTaskId {
                            flow = TaskActionFlow(taskId: taskId, itemId: item.id, itemTitle: item.title, action: action)
                        }
                    } label: {
                        Label(action.label, systemImage: action.systemImage).font(.system(size: 11, weight: .semibold))
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(appState.themeAccent)
                    .controlSize(.small)
                    .disabled(!action.available)
                    .help(action.available ? action.description : (action.reason ?? ""))
                }
            }
            ForEach(item.actions.filter { !$0.available }) { action in
                if let reason = action.reason {
                    Text("\(action.label): \(reason)").font(.system(size: 10)).foregroundColor(appState.themeTextSecondary)
                }
            }
        }
        .padding(.top, 2)
    }

    /// What was done with it: a checkout opened, a table booked.
    @ViewBuilder
    private func doneSection(_ item: AgentTaskItem) -> some View {
        let done = item.actionHistory.filter(\.isFinished)
        if !done.isEmpty {
            section("Done") {
                ForEach(done) { run in
                    HStack(spacing: 6) {
                        Image(systemName: run.status == "done" ? "checkmark.circle.fill" : "xmark.octagon")
                            .font(.system(size: 11))
                            .foregroundColor(run.status == "done" ? .green : .orange)
                        Text(TaskItemDetailView.doneLine(run))
                            .font(.system(size: 11))
                            .foregroundColor(appState.themeText)
                            .lineLimit(2)
                        Spacer(minLength: 4)
                        if run.status == "done", let url = TasksViewModel.webURL(run.result?.url) {
                            Link("Open", destination: url).font(.system(size: 11))
                        }
                    }
                }
            }
        }
    }

    /// Pressing the state it's already in puts it back to new.
    private func stateButton(_ label: String, state: String, icon: String, item: AgentTaskItem) -> some View {
        let on = item.userState == state
        return Button {
            Task { await vm.setState(on ? "new" : state, itemId: item.id) }
        } label: {
            Label(label, systemImage: on ? icon + ".fill" : icon).font(.system(size: 11))
        }
        .buttonStyle(.bordered)
        .controlSize(.small)
        .tint(on ? appState.themeAccent : nil)
        .disabled(vm.busy)
    }

    private func photos(_ item: AgentTaskItem) -> some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(item.images, id: \.url) { image in
                    if let url = TasksViewModel.webURL(image.url) {
                        AsyncImage(url: url) { phase in
                            if let picture = phase.image {
                                picture.resizable().scaledToFill()
                            } else {
                                Color.gray.opacity(0.1)
                            }
                        }
                        .frame(width: 150, height: 110)
                        .clipShape(RoundedRectangle(cornerRadius: 8))
                        .overlay(alignment: .bottomLeading) {
                            if image.screenshot {
                                Text("Its page")
                                    .font(.system(size: 9, weight: .semibold))
                                    .padding(.horizontal, 5).padding(.vertical, 2)
                                    .background(Capsule().fill(.black.opacity(0.55)))
                                    .foregroundColor(.white)
                                    .padding(5)
                            }
                        }
                        .help(image.alt ?? "")
                    }
                }
            }
        }
    }

    private func facts(_ item: AgentTaskItem) -> some View {
        let labels = Dictionary((vm.detail?.plan.columns ?? []).map { ($0.key, $0.label) },
                                uniquingKeysWith: { first, _ in first })
        let order = TaskItemDetailView.factOrder(item, columns: vm.detail?.plan.columns ?? [])
        return section("What it found") {
            if order.isEmpty {
                Text("No facts could be confirmed from its page.")
                    .font(.system(size: 11)).foregroundColor(appState.themeTextSecondary)
            }
            ForEach(order, id: \.self) { key in
                if let field = item.fields[key] {
                    FactRow(label: labels[key] ?? TaskItemDetailView.label(for: key), field: field)
                }
            }
            if !item.unconfirmed.isEmpty {
                Text("Couldn't confirm on its own page: " + item.unconfirmed
                    .map { labels[$0] ?? TaskItemDetailView.label(for: $0) }.joined(separator: ", ") + ".")
                    .font(.system(size: 10))
                    .foregroundColor(appState.themeTextSecondary)
            }
        }
    }

    @ViewBuilder
    private func homesSection(_ item: AgentTaskItem) -> some View {
        if !item.units.isEmpty {
            let ordered = TaskItemDetailView.homesOrder(item.units)
            let shown = allHomes ? ordered : Array(ordered.prefix(TaskItemDetailView.homesShown))
            section("Homes to let") {
                Text(item.homes?.line ?? "\(ordered.count) homes listed")
                    .font(.system(size: 11, weight: .medium))
                ForEach(shown) { unit in
                    UnitRow(unit: unit, buildingUrl: item.url)
                }
                if ordered.count > TaskItemDetailView.homesShown {
                    Button(allHomes ? "Show fewer" : "Show all \(ordered.count)") { allHomes.toggle() }
                        .buttonStyle(.link)
                        .font(.system(size: 11))
                }
                Text("From the building's leasing system. Net rent spreads a special's free weeks over the lease.")
                    .font(.system(size: 10))
                    .foregroundColor(appState.themeTextSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    @ViewBuilder
    private func fitSection(_ item: AgentTaskItem) -> some View {
        if !item.fitReasons.isEmpty || !item.violations.isEmpty {
            section("How it fits") {
                if let fit = item.fitScore {
                    Text("Fit \(fit)/5").font(.system(size: 11, weight: .semibold))
                }
                ForEach(item.fitReasons, id: \.self) { reason in
                    Label(reason, systemImage: "checkmark").font(.system(size: 11))
                }
                ForEach(item.violations, id: \.self) { violation in
                    Label("Breaks \u{201C}\(violation.rule ?? "")\u{201D}"
                          + (violation.value.map { ": \($0)" } ?? ""), systemImage: "xmark")
                        .font(.system(size: 11)).foregroundColor(.orange)
                }
            }
        }
    }

    private func notesSection(_ item: AgentTaskItem) -> some View {
        section("Your notes") {
            TextEditor(text: $notes)
                .font(.system(size: 12))
                // A fixed height: inside a scroll view an open-ended editor
                // grows without limit, and the window with it.
                .frame(height: 80)
                .scrollContentBackground(.hidden)
                .padding(6)
                .background(RoundedRectangle(cornerRadius: 6).fill(appState.themeText.opacity(0.04)))
            if notes != item.notes {
                Button("Save notes") { Task { await vm.saveNotes(notes, itemId: item.id) } }
                    .controlSize(.small)
                    .disabled(vm.busy)
            }
        }
    }

    private func actions(_ item: AgentTaskItem) -> some View {
        HStack(spacing: 8) {
            if vm.detail?.canFollowUp == true {
                Button {
                    Task { await vm.startRound(kind: "more", itemIds: [item.id]) }
                } label: { Label("More like this", systemImage: "plus.magnifyingglass") }
                .help("Search for more like this one. Uses 1 unit.")
                .disabled(vm.busy)
            }
            Button {
                if let taskId = vm.selectedTaskId {
                    appState.workOnTask(directive: "", taskId: taskId, itemId: item.id)
                }
            } label: { Label("Ask Espresso", systemImage: "bubble.left.and.text.bubble.right") }
        }
        .controlSize(.small)
    }

    private func section<Content: View>(_ title: String, @ViewBuilder _ content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title.uppercased())
                .font(.system(size: 9, weight: .semibold))
                .foregroundColor(appState.themeTextSecondary)
            content()
        }
    }

    // MARK: Pure helpers (tested)

    /// Homes shown before "Show all".
    nonisolated static let homesShown = 6

    /// The homes that meet every limit first, each group as the server sent
    /// it (cheapest first).
    nonisolated static func homesOrder(_ units: [AgentTaskUnit]) -> [AgentTaskUnit] {
        units.filter { $0.fits == true } + units.filter { $0.fits != true }
    }

    /// The plan's columns first, in its order, then any other fact.
    nonisolated static func factOrder(_ item: AgentTaskItem, columns: [AgentTaskColumn]) -> [String] {
        let first = columns.map(\.key).filter { item.fields[$0] != nil }
        return first + item.fields.keys.filter { !first.contains($0) }.sorted()
    }

    nonisolated static func label(for key: String) -> String {
        key.replacingOccurrences(of: "_", with: " ").capitalized
    }

    /// "Checkout opened at drbronner.com", or why it didn't go through.
    nonisolated static func doneLine(_ run: AgentTaskActionRun) -> String {
        if run.status == "done" { return run.result?.headline.isEmpty == false ? run.result!.headline : run.label }
        return "\(run.label) didn't go through" + (run.error.map { ": \($0)" } ?? ".")
    }
}

/// A fact, and on a tap what it rests on.
private struct FactRow: View {
    @Environment(AppState.self) private var appState
    let label: String
    let field: AgentTaskField
    @State private var showEvidence = false

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            Text(label)
                .font(.system(size: 11))
                .foregroundColor(appState.themeTextSecondary)
                .frame(width: 100, alignment: .leading)
            Text(field.display)
                .font(.system(size: 12, weight: .medium))
                .foregroundColor(appState.themeText)
            Text(field.isVerified ? "Verified" : "Unconfirmed")
                .font(.system(size: 9, weight: .semibold))
                .padding(.horizontal, 5).padding(.vertical, 1)
                .background(Capsule().fill((field.isVerified ? Color.green : Color.orange).opacity(0.15)))
                .foregroundColor(field.isVerified ? .green : .orange)
            Spacer(minLength: 0)
            if field.evidence?.quote != nil || field.evidence?.url != nil {
                Button { showEvidence.toggle() } label: {
                    Image(systemName: "quote.bubble").font(.system(size: 10))
                }
                .buttonStyle(.plain)
                .foregroundColor(appState.themeTextSecondary)
                .help("Where this came from")
                .popover(isPresented: $showEvidence) { evidence }
            }
        }
    }

    private var evidence: some View {
        VStack(alignment: .leading, spacing: 8) {
            if let origin = field.evidence?.originLabel, !origin.isEmpty {
                Text(origin).font(.system(size: 10, weight: .semibold)).foregroundColor(appState.themeTextSecondary)
            }
            if let quote = field.evidence?.quote {
                Text("\u{201C}\(quote)\u{201D}")
                    .font(.system(size: 12))
                    .italic()
                    .fixedSize(horizontal: false, vertical: true)
                    .textSelection(.enabled)
            }
            if let url = TasksViewModel.webURL(field.evidence?.url) {
                Link(destination: url) {
                    Label(TasksViewModel.linkLabel(url), systemImage: "arrow.up.right.square").font(.system(size: 11))
                }
            }
            if !field.isVerified {
                Text("This was stated on another page, not the finding's own, so it isn't used to rule anything in or out.")
                    .font(.system(size: 10))
                    .foregroundColor(appState.themeTextSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(14)
        .frame(width: 320)
    }
}

/// One home to let: its layout, rent (and net rent), move-in date, special,
/// floor plan and tour.
private struct UnitRow: View {
    @Environment(AppState.self) private var appState
    let unit: AgentTaskUnit
    let buildingUrl: String?
    @State private var showPlan = false

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            plan
            VStack(alignment: .leading, spacing: 3) {
                HStack(spacing: 6) {
                    Text(unit.layoutLine)
                        .font(.system(size: 11, weight: .semibold))
                        .lineLimit(1)
                    if unit.fits == true {
                        Text("Fits")
                            .font(.system(size: 9, weight: .semibold))
                            .padding(.horizontal, 5).padding(.vertical, 1)
                            .background(Capsule().fill(Color.green.opacity(0.15)))
                            .foregroundColor(.green)
                            .help("Meets every limit you set")
                    }
                }
                HStack(spacing: 6) {
                    Text("\(AgentTaskUnit.dollars(unit.rent))/mo")
                        .font(.system(size: 12, weight: .medium))
                    if let net = unit.netRent {
                        Text("\(AgentTaskUnit.dollars(net))/mo net")
                            .font(.system(size: 11, weight: .medium))
                            .foregroundColor(.green)
                            .help(unit.netNote ?? "")
                    }
                }
                let terms = [unit.availableLabel().map { $0 == "Now" ? "Available now" : "Available \($0)" },
                             unit.leaseMonths.map { "\($0)-month lease" }, unit.plan].compactMap { $0 }
                if !terms.isEmpty {
                    Text(terms.joined(separator: " · "))
                        .font(.system(size: 10))
                        .foregroundColor(appState.themeTextSecondary)
                        .lineLimit(1)
                }
                if let special = unit.special {
                    Label(special, systemImage: "tag")
                        .font(.system(size: 10))
                        .foregroundColor(.orange)
                        .lineLimit(2)
                }
                HStack(spacing: 12) {
                    if let tour = TasksViewModel.webURL(unit.tourUrl) {
                        Link(destination: tour) { Label("3D tour", systemImage: "cube.transparent") }
                    }
                    if unit.url != buildingUrl, let page = TasksViewModel.webURL(unit.url) {
                        Link(destination: page) { Label("Its page", systemImage: "arrow.up.right.square") }
                    }
                }
                .font(.system(size: 10))
            }
            Spacer(minLength: 0)
        }
        .padding(8)
        .background(RoundedRectangle(cornerRadius: 8)
            .fill(unit.fits == true ? Color.green.opacity(0.06) : appState.themeText.opacity(0.03)))
    }

    @ViewBuilder
    private var plan: some View {
        if let url = TasksViewModel.webURL(unit.planImage) {
            Button { showPlan.toggle() } label: {
                AsyncImage(url: url) { phase in
                    if let picture = phase.image {
                        picture.resizable().scaledToFit()
                    } else {
                        Color.gray.opacity(0.1)
                    }
                }
                .frame(width: 56, height: 56)
                .background(Color.white)
                .clipShape(RoundedRectangle(cornerRadius: 6))
            }
            .buttonStyle(.plain)
            .help("Floor plan")
            .popover(isPresented: $showPlan) {
                AsyncImage(url: url) { phase in
                    if let picture = phase.image {
                        picture.resizable().scaledToFit()
                    } else {
                        ProgressView()
                    }
                }
                .frame(width: 420, height: 420)
                .background(Color.white)
                .padding(10)
            }
        } else {
            RoundedRectangle(cornerRadius: 6)
                .fill(appState.themeText.opacity(0.05))
                .frame(width: 56, height: 56)
                .overlay(Image(systemName: "square.split.2x2").foregroundColor(appState.themeTextSecondary))
                .help("No floor plan")
        }
    }
}
