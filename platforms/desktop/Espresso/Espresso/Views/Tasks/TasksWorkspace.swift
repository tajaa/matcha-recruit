import SwiftUI
import AppKit

/// The Tasks section: the person's background tasks on the left (needs you,
/// running, done), the open task's findings in the middle, and the open
/// finding (each fact with the words and page it came from) on the right.
/// A job search is a task too; it opens in the search's own view.
struct TasksWorkspace: View {
    @Environment(AppState.self) private var appState
    @State private var vm = TasksViewModel()
    /// Starting a job search (its sheet needs the allowance and consent).
    @State private var jobs = JobSearchViewModel()
    @State private var showNewJobSearch = false
    @State private var newDirective = ""
    @State private var showRefine = false
    @State private var refineText = ""
    @State private var deleting: AgentTask?
    @State private var madeJournal: String?

    var body: some View {
        HStack(spacing: 0) {
            rail.frame(width: 250)
            Divider().opacity(0.2)
            if let search = vm.selectedTask, search.isJobSearch, let searchId = search.jobSearchId {
                JobSearchDetailView(searchId: searchId, focusLeadId: vm.jobLeadFocus)
                    .id(searchId)
            } else {
                // A floor on the middle column: with none, working out the window's
                // minimum size squeezes it to nothing and any wrapping text in it
                // becomes a column thousands of points tall.
                content.frame(minWidth: 380, maxWidth: .infinity, maxHeight: .infinity)
            }
            if vm.selectedItemId != nil, !(vm.selectedTask?.isJobSearch ?? false) {
                Divider().opacity(0.2)
                TaskItemDetailView(vm: vm, onClose: { Task { await vm.selectItem(nil) } })
                    .frame(width: 420)
            }
        }
        .background(ThemeRadialBackground())
        .featureGuideOnFirstVisit(.tasks)
        .task(id: appState.currentUser?.id) {
            vm.reset()
            await openFocus()
            await vm.load()
            var sinceList: UInt64 = 0
            while !Task.isCancelled {
                let live = vm.detail?.task.isLive ?? false
                let wait = TasksViewModel.pollSeconds(live: live)
                try? await Task.sleep(for: .seconds(Int(wait)))
                guard !Task.isCancelled else { break }
                await vm.poll()
                sinceList += wait
                if sinceList >= 30 {
                    sinceList = 0
                    await vm.refreshList()
                    await appState.refreshTasksSummary()
                }
            }
        }
        .onChange(of: appState.tasksFocus) { _, _ in Task { await openFocus() } }
        .onChange(of: vm.planFeature) { _, feature in
            if let feature { appState.presentPaywall(for: feature); vm.planFeature = nil }
        }
        .confirmationDialog(
            "Delete this task?",
            isPresented: Binding(get: { deleting != nil }, set: { if !$0 { deleting = nil } }),
            presenting: deleting
        ) { task in
            Button("Delete", role: .destructive) { Task { await vm.delete(task.id) } }
        } message: { task in
            Text(task.isJobSearch
                 ? "Its jobs and drafts are removed. It still counts toward this month's units."
                 : "What it found is removed. It still counts toward this month's units.")
        }
        .sheet(isPresented: $showNewJobSearch, onDismiss: openCreatedSearch) {
            NewJobSearchSheet(vm: jobs).environment(appState)
        }
    }

    /// A task the app was asked to show (a chat card, a notification).
    private func openFocus() async {
        guard let focus = appState.tasksFocus else { return }
        appState.tasksFocus = nil
        await vm.open(focus)
    }

    private func startJobSearch() {
        Task {
            await jobs.prepareNew()
            showNewJobSearch = true
        }
    }

    /// The sheet closed: open the search it started, if it started one.
    private func openCreatedSearch() {
        guard let searchId = jobs.createdSearchId else { return }
        jobs.createdSearchId = nil
        Task {
            await vm.open(TasksFocus(taskId: nil, jobSearchId: searchId))
            await appState.refreshTasksSummary()
        }
    }

    // MARK: Rail

    private var rail: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Text("Tasks")
                    .font(.system(size: 15, weight: .bold))
                    .foregroundColor(appState.themeText)
                Spacer()
                FeatureGuideButton(id: .tasks)
            }
            .padding(.horizontal, 14).padding(.top, 14).padding(.bottom, 8)
            if appState.tasksEnabled {
                newTaskBox
                    .padding(.horizontal, 10).padding(.bottom, appState.jobSearchEnabled ? 2 : 8)
            }
            if appState.jobSearchEnabled {
                newJobSearchButton
                    .padding(.horizontal, 10).padding(.bottom, 8)
            }
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 2, pinnedViews: []) {
                    ForEach(vm.groups, id: \.0) { group, tasks in
                        Text(group.rawValue.uppercased())
                            .font(.system(size: 9, weight: .semibold))
                            .foregroundColor(group == .needsYou ? .orange : appState.themeTextSecondary)
                            .padding(.horizontal, 8).padding(.top, 10).padding(.bottom, 2)
                        ForEach(tasks) { task in taskRow(task) }
                    }
                }
                .padding(.horizontal, 8)
            }
            Spacer(minLength: 0)
            if let line = TasksViewModel.usageLine(vm.usage) {
                Text(line)
                    .font(.system(size: 10))
                    .foregroundColor(appState.themeTextSecondary)
                    .padding(.horizontal, 14).padding(.vertical, 10)
            }
        }
    }

    /// Directive-first: what to do goes to Espresso, which asks for anything
    /// missing with a form and starts the task.
    private var newTaskBox: some View {
        VStack(alignment: .leading, spacing: 6) {
            TextField("What should Espresso go and do?", text: $newDirective, axis: .vertical)
                .textFieldStyle(.roundedBorder)
                .font(.system(size: 12))
                .lineLimit(1...4)
                .onSubmit(startTask)
            HStack {
                Text("Espresso asks for what it needs, then works in the background.")
                    .font(.system(size: 9))
                    .foregroundColor(appState.themeTextSecondary)
                    .lineLimit(2)
                Spacer(minLength: 4)
                Button("Ask Espresso", action: startTask)
                    .controlSize(.small)
                    .disabled(newDirective.trimmingCharacters(in: .whitespacesAndNewlines).count < 3)
            }
        }
    }

    /// Job searches start here too (or from chat, as a task).
    @ViewBuilder
    private var newJobSearchButton: some View {
        if appState.tasksEnabled {
            Button(action: startJobSearch) {
                Label("New job search…", systemImage: "briefcase").font(.system(size: 10))
            }
            .buttonStyle(.plain)
            .foregroundColor(appState.themeAccent)
        } else {
            Button(action: startJobSearch) {
                Label("New job search", systemImage: "briefcase")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.bordered)
        }
    }

    private func startTask() {
        let directive = newDirective.trimmingCharacters(in: .whitespacesAndNewlines)
        guard directive.count >= 3 else { return }
        newDirective = ""
        appState.workOnTask(directive: directive)
    }

    private func taskRow(_ task: AgentTask) -> some View {
        let selected = vm.selectedTaskId == task.id
        return Button {
            Task { await vm.select(task.id) }
        } label: {
            HStack(alignment: .top, spacing: 6) {
                Circle()
                    .fill(task.unseen ? appState.themeAccent : Color.clear)
                    .frame(width: 6, height: 6)
                    .padding(.top, 5)
                VStack(alignment: .leading, spacing: 3) {
                    Text(task.displayTitle)
                        .font(.system(size: 12, weight: task.unseen ? .bold : .semibold))
                        .foregroundColor(appState.themeText)
                        .lineLimit(2)
                    HStack(spacing: 5) {
                        if task.isJobSearch {
                            Image(systemName: "briefcase").help("Job search")
                        }
                        if task.isLive { ProgressView().controlSize(.mini) }
                        Text(task.statusLabel)
                        if task.shownCount > 0 {
                            Text("\u{00B7} \(task.shownCount) \(task.isJobSearch ? "jobs" : "found")")
                        }
                    }
                    .font(.system(size: 10))
                    .foregroundColor(task.isWaiting ? .orange : appState.themeTextSecondary)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 6).padding(.vertical, 7)
            .contentShape(Rectangle())
            .background(RoundedRectangle(cornerRadius: 6)
                .fill(selected ? appState.themeAccent.opacity(0.1) : Color.clear))
        }
        .buttonStyle(.plain)
        .contextMenu {
            Button("Delete…", role: .destructive) { deleting = task }
        }
    }

    // MARK: Content

    @ViewBuilder
    private var content: some View {
        if !vm.hasLoaded && vm.errorMessage == nil {
            ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if !vm.hasLoaded, let error = vm.errorMessage {
            // Never the empty state: someone with tasks would think they were gone.
            emptyState(icon: "exclamationmark.triangle", title: "Couldn't load your tasks", text: error)
        } else if vm.tasks.isEmpty && !appState.tasksEnabled {
            emptyState(
                icon: "briefcase",
                title: "Start a job search",
                text: "Say what you're after (\u{201C}COO roles across the US, mostly about salary, bonus "
                    + "and equity\u{201D}). Espresso finds the postings, reads each one for pay and what the "
                    + "application asks, ranks them by what you care about, and drafts how to approach the best "
                    + "ones. Nothing is sent or submitted for you."
            )
        } else if vm.tasks.isEmpty {
            emptyState(
                icon: "list.bullet.clipboard",
                title: "Give Espresso something to go and do",
                text: "\u{201C}Find me a 1-bedroom in SF under $3,500 that allows dogs.\u{201D} \u{201C}The best "
                    + "organic lip balm under $15.\u{201D} Espresso asks for anything it needs, works in the "
                    + "background, and keeps what it finds here with where each fact came from. Then refine "
                    + "it, ask for more, or turn it into a document."
            )
        } else if let detail = vm.detail {
            VStack(spacing: 0) {
                header(detail)
                Divider().opacity(0.2)
                if let error = vm.errorMessage { errorBanner(error) }
                if let journal = madeJournal { documentBanner(journal) }
                filters(detail)
                findings(detail)
            }
        } else {
            VStack {
                if let error = vm.errorMessage { errorBanner(error) }
                ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
    }

    private func header(_ detail: AgentTaskDetail) -> some View {
        let task = detail.task
        return VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .firstTextBaseline, spacing: 10) {
                Text(task.displayTitle)
                    .font(.system(size: 18, weight: .bold))
                    .foregroundColor(appState.themeText)
                    .lineLimit(1)
                Spacer(minLength: 8)
                Button {
                    appState.workOnTask(directive: "", taskId: task.id)
                } label: { Image(systemName: "bubble.left.and.text.bubble.right") }
                .buttonStyle(.plain)
                .foregroundColor(appState.themeTextSecondary)
                .help("Ask Espresso about this task")
            }
            if !task.directive.isEmpty && task.directive != task.displayTitle {
                Text(task.directive)
                    .font(.system(size: 11))
                    .foregroundColor(appState.themeTextSecondary)
                    .lineLimit(2)
            }
            if !detail.plan.constraints.isEmpty || detail.plan.location != nil {
                TaskChips(items: ([detail.plan.location].compactMap { $0 } + detail.plan.constraints.map(\.label)))
            }
            HStack(spacing: 6) {
                if task.isLive { ProgressView().controlSize(.mini) }
                Text(task.isLive ? (task.progress.note ?? task.statusLabel) : task.statusLabel)
                    .font(.system(size: 11, weight: .medium))
                    .foregroundColor(task.status == "failed" ? .orange : appState.themeTextSecondary)
                if let error = task.error, task.status == "failed" {
                    Text(error).font(.system(size: 11)).foregroundColor(.orange).lineLimit(2)
                }
            }
            if let summary = detail.latestSummary, !task.isLive {
                VStack(alignment: .leading, spacing: 4) {
                    if let headline = summary.headline {
                        Text(headline).font(.system(size: 13, weight: .semibold)).foregroundColor(appState.themeText)
                            .lineLimit(3)
                    }
                    if let text = summary.summary, !text.isEmpty {
                        Text(text).font(.system(size: 12)).foregroundColor(appState.themeTextSecondary)
                            .lineLimit(6)
                    }
                }
                .padding(10)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(RoundedRectangle(cornerRadius: 8).fill(appState.themeText.opacity(0.04)))
            }
            // Their own row, so they never truncate when a finding is open beside.
            actions(detail)
        }
        .padding(.horizontal, 18).padding(.vertical, 14)
    }

    @ViewBuilder
    private func actions(_ detail: AgentTaskDetail) -> some View {
        let task = detail.task
        HStack(spacing: 8) {
            if task.isLive || task.isWaiting {
                Button("Cancel") { Task { await vm.cancel() } }
                    .buttonStyle(.bordered).disabled(vm.busy)
            }
            if detail.canFollowUp {
                Button { showRefine = true } label: { Label("Refine", systemImage: "slider.horizontal.3") }
                    .disabled(vm.busy)
                    .help("Change what it's looking for. Free.")
                    .popover(isPresented: $showRefine) { refinePopover }
                Button { Task { await vm.startRound(kind: "more") } } label: {
                    Label("Search more", systemImage: "plus.magnifyingglass")
                }
                .disabled(vm.busy)
                .help("Look for more like these. Uses 1 unit.")
            }
            if !task.isLive && !detail.items.isEmpty {
                Button {
                    Task {
                        madeJournal = await vm.startRound(kind: "document")
                    }
                } label: { Label("Make document", systemImage: "doc.text") }
                .disabled(vm.busy)
                .help("Write what it found into a note. Free.")
            }
        }
        .controlSize(.small)
    }

    private var refinePopover: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("What should change?").font(.system(size: 13, weight: .semibold))
            TextField("Only the Mission, and a dishwasher", text: $refineText, axis: .vertical)
                .textFieldStyle(.roundedBorder)
                .lineLimit(2...5)
            Text("Espresso re-checks what it found against the change, reads pages again only for new facts, "
                 + "and searches again if too little is left. Free.")
                .font(.system(size: 10))
                .foregroundColor(appState.themeTextSecondary)
                .fixedSize(horizontal: false, vertical: true)
            HStack {
                Spacer()
                Button("Refine") {
                    let change = refineText.trimmingCharacters(in: .whitespacesAndNewlines)
                    showRefine = false
                    refineText = ""
                    Task { await vm.startRound(kind: "refine", directive: change) }
                }
                .buttonStyle(.borderedProminent)
                .tint(appState.themeAccent)
                .disabled(refineText.trimmingCharacters(in: .whitespacesAndNewlines).count < 3)
            }
        }
        .padding(16)
        .frame(width: 320)
    }

    private func filters(_ detail: AgentTaskDetail) -> some View {
        HStack(spacing: 10) {
            Picker("", selection: $vm.filter) {
                ForEach(TasksViewModel.Filter.allCases) { Text($0.rawValue).tag($0) }
            }
            .pickerStyle(.segmented)
            .labelsHidden()
            .frame(maxWidth: 280)
            Spacer()
            Text("\(detail.visibleItems.count) fit \u{00B7} \(detail.hiddenItems.count) hidden")
                .font(.system(size: 10))
                .foregroundColor(appState.themeTextSecondary)
        }
        .padding(.horizontal, 18).padding(.vertical, 8)
    }

    private func findings(_ detail: AgentTaskDetail) -> some View {
        ScrollView {
            LazyVStack(spacing: 4) {
                ForEach(vm.visibleItems) { item in
                    TaskFindingRow(item: item, columns: detail.plan.columns,
                                   selected: vm.selectedItemId == item.id) {
                        Task { await vm.selectItem(item.id) }
                    }
                }
                if vm.visibleItems.isEmpty {
                    Text(detail.task.isLive ? "Nothing yet. It's still looking." : "Nothing here.")
                        .font(.system(size: 12))
                        .foregroundColor(appState.themeTextSecondary)
                        .padding(.top, 30)
                }
            }
            .padding(.horizontal, 14).padding(.bottom, 14)
        }
    }

    // MARK: Pieces

    private func emptyState(icon: String, title: String, text: String) -> some View {
        VStack(spacing: 10) {
            Image(systemName: icon)
                .font(.system(size: 30))
                .foregroundColor(appState.themeTextSecondary.opacity(0.7))
            Text(title)
                .font(.system(size: 14, weight: .semibold))
                .foregroundColor(appState.themeText)
            Text(text)
                .font(.system(size: 12))
                .foregroundColor(appState.themeTextSecondary)
                .multilineTextAlignment(.center)
                .frame(maxWidth: 460)
            if let line = TasksViewModel.usageLine(vm.usage) {
                Text(line).font(.system(size: 10)).foregroundColor(appState.themeTextSecondary)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

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

    private func documentBanner(_ journalId: String) -> some View {
        HStack(spacing: 6) {
            Image(systemName: "doc.text.fill").font(.system(size: 10))
            Text("The document is in your Journals.").font(.system(size: 11))
            Button("Open") { appState.showInMain(.journal(journalId)) }
                .buttonStyle(.link).font(.system(size: 11))
            Spacer()
            Button { madeJournal = nil } label: {
                Image(systemName: "xmark").font(.system(size: 9, weight: .bold))
            }
            .buttonStyle(.plain)
        }
        .foregroundColor(appState.themeAccent)
        .padding(.horizontal, 18).padding(.vertical, 6)
        .background(appState.themeAccent.opacity(0.08))
    }
}

/// One finding: rank, photo, name, and the facts the plan asked for, each
/// marked when it couldn't be confirmed on the finding's own page.
struct TaskFindingRow: View {
    @Environment(AppState.self) private var appState
    let item: AgentTaskItem
    let columns: [AgentTaskColumn]
    let selected: Bool
    let onTap: () -> Void

    var body: some View {
        Button(action: onTap) {
            HStack(alignment: .top, spacing: 10) {
                Text(item.rank.map(String.init) ?? "")
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundColor(appState.themeTextSecondary)
                    .frame(width: 22, alignment: .trailing)
                thumbnail
                VStack(alignment: .leading, spacing: 4) {
                    HStack(spacing: 6) {
                        Text(item.title).font(.system(size: 12, weight: .semibold)).lineLimit(1)
                        if item.userState == "saved" || item.userState == "chosen" {
                            Image(systemName: item.userState == "chosen" ? "checkmark.seal.fill" : "bookmark.fill")
                                .font(.system(size: 9)).foregroundColor(appState.themeAccent)
                        }
                    }
                    if !item.subtitle.isEmpty {
                        Text(item.subtitle).font(.system(size: 11))
                            .foregroundColor(appState.themeTextSecondary).lineLimit(1)
                    }
                    HStack(spacing: 6) {
                        ForEach(columns.prefix(5)) { column in
                            if let field = item.fields[column.key] {
                                FactChip(label: column.label, field: field)
                            }
                        }
                    }
                    if let reason = item.hiddenReason {
                        Text(reason).font(.system(size: 10)).foregroundColor(.orange)
                    } else if !item.unconfirmed.isEmpty {
                        Text("Unconfirmed: " + item.unconfirmed.map { key in
                            columns.first { $0.key == key }?.label ?? TaskItemDetailView.label(for: key)
                        }.joined(separator: ", "))
                            .font(.system(size: 10)).foregroundColor(appState.themeTextSecondary)
                    }
                }
                Spacer(minLength: 0)
            }
            .padding(8)
            .frame(maxWidth: .infinity, alignment: .leading)
            .contentShape(Rectangle())
            .background(RoundedRectangle(cornerRadius: 8)
                .fill(selected ? appState.themeAccent.opacity(0.1) : appState.themeText.opacity(0.03)))
        }
        .buttonStyle(.plain)
        .foregroundColor(appState.themeText)
    }

    @ViewBuilder
    private var thumbnail: some View {
        if let image = item.images.first, let url = TasksViewModel.webURL(image.url) {
            AsyncImage(url: url) { phase in
                if let picture = phase.image {
                    picture.resizable().scaledToFill()
                } else {
                    Color.gray.opacity(0.1)
                }
            }
            .frame(width: 46, height: 46)
            .clipShape(RoundedRectangle(cornerRadius: 6))
        }
    }
}

/// "Price $3,200/mo", dimmed and marked when only claimed elsewhere.
struct FactChip: View {
    @Environment(AppState.self) private var appState
    let label: String
    let field: AgentTaskField

    var body: some View {
        HStack(spacing: 3) {
            Text(label).foregroundColor(appState.themeTextSecondary)
            Text(field.display).fontWeight(.medium)
            if !field.isVerified {
                Image(systemName: "questionmark.circle").foregroundColor(.orange)
            }
        }
        .font(.system(size: 10))
        .lineLimit(1)
        .padding(.horizontal, 6).padding(.vertical, 2)
        .background(Capsule().fill(appState.themeText.opacity(0.06)))
        .help(field.isVerified ? "Read on its own page" : "Unconfirmed: only stated on another page")
    }
}

/// What a task is looking for, as chips that wrap.
struct TaskChips: View {
    @Environment(AppState.self) private var appState
    let items: [String]

    var body: some View {
        ViewThatFits(in: .horizontal) {
            HStack(spacing: 6) { chips }
            ScrollView(.horizontal, showsIndicators: false) { HStack(spacing: 6) { chips } }
        }
    }

    private var chips: some View {
        ForEach(items, id: \.self) { text in
            Text(text)
                .font(.system(size: 10, weight: .medium))
                .padding(.horizontal, 7).padding(.vertical, 3)
                .background(Capsule().fill(appState.themeAccent.opacity(0.1)))
                .foregroundColor(appState.themeText)
        }
    }
}
