import Foundation
import Observation

/// The Tasks section: the person's tasks, the open one's findings, and the
/// open finding. Polls a live task's cheap status every few seconds and
/// reloads only when its fingerprint changes.
@Observable @MainActor
final class TasksViewModel {
    enum Filter: String, CaseIterable, Identifiable {
        case fits = "Fits"
        case saved = "Saved"
        case hidden = "Hidden"
        var id: String { rawValue }
    }

    var tasks: [AgentTask] = []
    var usage: AgentTaskUnits?
    var hasLoaded = false

    var selectedTaskId: String?
    /// A job to open in the selected job search (a chat card, a link).
    var jobLeadFocus: String?
    var detail: AgentTaskDetail?
    var selectedItemId: String?
    var item: AgentTaskItem?
    var itemLoading = false

    var filter: Filter = .fits
    var busy = false
    var errorMessage: String?
    /// A 403 that names a plan: the view raises the paywall for it.
    var planFeature: String?

    private let service = AgentTaskService.shared

    var selectedTask: AgentTask? { detail?.task ?? tasks.first { $0.id == selectedTaskId } }
    var visibleItems: [AgentTaskItem] { Self.filtered(detail?.items ?? [], filter: filter) }
    var groups: [(AgentTaskGroup, [AgentTask])] { AgentTaskGroup.grouped(tasks) }

    // MARK: Loading

    func load() async {
        do {
            let list = try await service.list()
            try Task.checkCancellation()
            tasks = list.tasks
            usage = list.usage
            if !hasLoaded { errorMessage = nil }
            hasLoaded = true
            if let id = selectedTaskId, !tasks.contains(where: { $0.id == id }) {
                selectedTaskId = nil; detail = nil; selectedItemId = nil; item = nil
            }
            if selectedTaskId == nil, let first = groups.first?.1.first {
                await select(first.id)
            } else if let id = selectedTaskId, detail == nil {
                await loadDetail(id)
            }
        } catch is CancellationError {
        } catch { report(error) }
    }

    /// Open what the app was asked to show: a task, or a job search by its id.
    func open(_ focus: TasksFocus) async {
        if let taskId = focus.taskId {
            await select(taskId, itemId: focus.itemId)
            return
        }
        guard let searchId = focus.jobSearchId else { return }
        if Self.task(forSearch: searchId, in: tasks) == nil { await refreshList() }
        guard let task = Self.task(forSearch: searchId, in: tasks) else { return }
        await select(task.id)
        jobLeadFocus = focus.leadId
    }

    func select(_ taskId: String, itemId: String? = nil) async {
        if selectedTaskId != taskId {
            selectedTaskId = taskId
            detail = nil
            selectedItemId = nil
            item = nil
            jobLeadFocus = nil
            filter = .fits
        }
        await loadDetail(taskId)
        if let itemId { await selectItem(itemId) }
    }

    private func loadDetail(_ taskId: String) async {
        do {
            let loaded = try await service.detail(taskId)
            try Task.checkCancellation()
            guard selectedTaskId == taskId else { return }
            apply(loaded)
            if let itemId = selectedItemId, !loaded.items.contains(where: { $0.id == itemId }) {
                selectedItemId = nil; item = nil
            }
        } catch is CancellationError {
        } catch { report(error) }
    }

    private func apply(_ loaded: AgentTaskDetail) {
        detail = loaded
        var seen = loaded.task
        seen.unseen = false  // opening it is what marks it seen
        if let i = tasks.firstIndex(where: { $0.id == seen.id }) {
            tasks[i] = seen
        } else {
            tasks.insert(seen, at: 0)
        }
    }

    /// The poll: cheap status, full reload only on a change.
    func poll() async {
        guard let id = selectedTaskId, let current = detail, current.task.isLive else { return }
        do {
            let status = try await service.status(id)
            try Task.checkCancellation()
            guard selectedTaskId == id else { return }
            if Self.changed(current, status) {
                await loadDetail(id)
                if let itemId = selectedItemId { await refreshItem(itemId) }
                if !(detail?.task.isLive ?? false) { await refreshList() }
            }
        } catch is CancellationError {
        } catch { report(error) }
    }

    /// The list on its slower beat, for tasks other than the open one.
    func refreshList() async {
        if let list = try? await service.list() {
            usage = list.usage
            tasks = list.tasks.map { task in
                // The open task stays seen while it is on screen.
                var task = task
                if task.id == selectedTaskId { task.unseen = false }
                return task
            }
        }
    }

    func selectItem(_ itemId: String?) async {
        selectedItemId = itemId
        guard let itemId else { item = nil; return }
        if item?.id != itemId { item = nil }
        await refreshItem(itemId)
    }

    private func refreshItem(_ itemId: String) async {
        guard let taskId = selectedTaskId else { return }
        itemLoading = true
        defer { itemLoading = false }
        do {
            let loaded = try await service.item(taskId, itemId)
            try Task.checkCancellation()
            if selectedItemId == itemId { item = loaded }
        } catch is CancellationError {
        } catch { report(error) }
    }

    // MARK: Actions

    /// Saved / Chosen / Dismissed (or back to New) for the finding acted on.
    func setState(_ state: String, itemId: String) async {
        guard let taskId = selectedTaskId else { return }
        await perform {
            let updated = try await self.service.updateItem(taskId, itemId, state: state)
            if self.selectedItemId == updated.id { self.item = updated }
            await self.loadDetail(taskId)
        }
    }

    func saveNotes(_ notes: String, itemId: String) async {
        guard let taskId = selectedTaskId else { return }
        await perform {
            let updated = try await self.service.updateItem(taskId, itemId, notes: notes)
            if self.selectedItemId == updated.id { self.item = updated }
        }
    }

    /// A refine, "search more" or a document. Returns the document's journal
    /// id when one was written, so the view can offer to open it.
    @discardableResult
    func startRound(kind: String, directive: String = "", itemIds: [String] = []) async -> String? {
        guard let taskId = selectedTaskId else { return nil }
        var journal: String?
        await perform {
            let updated = try await self.service.startRound(taskId, kind: kind, directive: directive, itemIds: itemIds)
            self.apply(updated)
            if kind == "document" { journal = updated.rounds.last?.document?.journalId }
            await self.refreshList()
        }
        return journal
    }

    func cancel() async {
        guard let taskId = selectedTaskId else { return }
        await perform { self.apply(try await self.service.cancel(taskId)) }
    }

    func delete(_ taskId: String) async {
        await perform {
            try await self.service.delete(taskId)
            if self.selectedTaskId == taskId {
                self.selectedTaskId = nil; self.detail = nil; self.selectedItemId = nil; self.item = nil
            }
            await self.load()
        }
    }

    private func perform(_ action: @escaping () async throws -> Void) async {
        guard !busy else { return }
        busy = true
        errorMessage = nil
        defer { busy = false }
        do { try await action() } catch { report(error) }
    }

    func report(_ error: Error) {
        if let api = error as? APIError {
            if let plan = api.planRequirement { planFeature = plan.feature }
            errorMessage = AssistantText.message(for: api)
        } else {
            errorMessage = error.localizedDescription
        }
    }

    /// The person signed out, or another account signed in.
    func reset() {
        tasks = []; usage = nil; hasLoaded = false
        selectedTaskId = nil; detail = nil; selectedItemId = nil; item = nil; jobLeadFocus = nil
        errorMessage = nil; planFeature = nil
    }

    // MARK: Pure helpers (tested)

    nonisolated static func changed(_ detail: AgentTaskDetail, _ status: AgentTaskStatus) -> Bool {
        status.fingerprint != detail.fingerprint || status.status != detail.task.status
    }

    nonisolated static func filtered(_ items: [AgentTaskItem], filter: Filter) -> [AgentTaskItem] {
        switch filter {
        case .fits: return items.filter { !$0.isHidden }
        case .saved: return items.filter { $0.userState == "saved" || $0.userState == "chosen" }
        case .hidden: return items.filter(\.isHidden)
        }
    }

    /// The task that is this job search.
    nonisolated static func task(forSearch searchId: String, in tasks: [AgentTask]) -> AgentTask? {
        tasks.first { $0.isJobSearch && $0.jobSearchId == searchId }
    }

    nonisolated static func usageLine(_ usage: AgentTaskUnits?) -> String? {
        guard let usage, usage.limit > 0 else { return nil }
        return "\(usage.remaining) of \(usage.limit) task units left this month"
    }

    /// How often to poll: quickly while something runs, slowly otherwise.
    nonisolated static func pollSeconds(live: Bool) -> UInt64 { live ? 4 : 30 }

    /// Only plain http(s) links are opened.
    nonisolated static func webURL(_ value: String?) -> URL? {
        guard let value, let url = URL(string: value),
              let scheme = url.scheme?.lowercased(), scheme == "http" || scheme == "https",
              url.host() != nil else { return nil }
        return url
    }

    /// What a link is called: the site ("drbronner.com"), or which part of
    /// Google it is when a finding only has Google's page.
    nonisolated static func linkLabel(_ url: URL) -> String {
        guard let host = url.host()?.lowercased() else { return "Open its page" }
        let site = host.hasPrefix("www.") ? String(host.dropFirst(4)) : host
        guard site.split(separator: ".").contains("google") else { return site }
        let path = url.path().lowercased()
        if path.hasPrefix("/maps") { return "Google Maps" }
        if path.hasPrefix("/shopping") || url.query()?.contains("ibp=oshop") == true { return "Google Shopping" }
        return site
    }

    /// The sidebar badge: how many run, and whether something needs the person.
    nonisolated static func badge(_ summary: AgentTasksSummary?) -> (count: Int, attention: Bool) {
        guard let summary else { return (0, false) }
        return (summary.running, summary.waiting > 0 || summary.unseen > 0)
    }
}
