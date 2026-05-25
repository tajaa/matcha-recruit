import Foundation
import AppKit
import UniformTypeIdentifiers

struct CollabActivityItem: Identifiable, Hashable {
    let id = UUID()
    let icon: String
    let text: String
    let timestamp: Date
}

@Observable
class ProjectDetailViewModel {
    var project: MWProject?
    var activeChatId: String?
    var isLoading = false
    var errorMessage: String?
    var tasks: [MWProjectTask] = []
    var isLoadingTasks = false
    var files: [MWProjectFile] = []
    var folders: [MWProjectFolder] = []
    var links: [MWProjectLink] = []
    var isLoadingFiles = false
    var collaborators: [MWProjectCollaborator] = []
    var elements: [MWProjectElement] = []
    /// Attachments per task, keyed by task id. Seeded by `loadTasks`
    /// (server embeds `attachments` per task) and updated by add/delete.
    var taskFiles: [String: [MWProjectFile]] = [:]
    /// Checklist items per task, keyed by task id. Loaded lazily when a task
    /// viewer opens; mutated optimistically. `syncSubtaskCounts` mirrors the
    /// counts onto the matching `tasks` entry so the card face updates live.
    var taskSubtasks: [String: [MWSubtask]] = [:]
    /// Per-session activity log surfaced in the collab Overview panel. Capped
    /// at 20 entries; FIFO eviction. In-memory only — survives panel switches
    /// but not project switches or app relaunches. Backend feed is a follow-up.
    var recentActivity: [CollabActivityItem] = []

    private let service = MatchaWorkService.shared
    /// Logged-in user — used to suppress self-echoes from the project WS
    /// task event fan-out (we already applied the change optimistically).
    var currentUserId: String?

    func logActivity(_ icon: String, _ text: String) {
        recentActivity.insert(
            CollabActivityItem(icon: icon, text: text, timestamp: Date()),
            at: 0
        )
        if recentActivity.count > 20 {
            recentActivity.removeLast(recentActivity.count - 20)
        }
    }

    /// Pull recent project activity from the server feed (task history,
    /// file uploads, collaborator joins) and replace the in-session list.
    /// Called on project open in addition to the existing in-session
    /// `logActivity(...)` calls (which still drive optimistic UI for the
    /// actor's own moves).
    @MainActor
    func loadProjectActivity() async {
        guard let pid = project?.id else { return }
        if let rows = try? await service.fetchProjectActivity(projectId: pid, limit: 20) {
            recentActivity = rows.compactMap(Self.mapActivity)
        }
    }

    private static func mapActivity(_ row: MWProjectActivityEntry) -> CollabActivityItem? {
        let who = row.actorName?.isEmpty == false ? row.actorName! : "Someone"
        let date = parseMWDate(row.createdAt) ?? Date()
        switch row.source {
        case "task_history":
            let event = row.string("event_type") ?? ""
            let title = row.string("task_title") ?? "a task"
            switch event {
            case "created":
                return .init(icon: "plus.circle", text: "\(who) created \(title)", timestamp: date)
            case "column_change":
                let from = row.string("from_value")?.replacingOccurrences(of: "_", with: " ").capitalized ?? "?"
                let to = row.string("to_value")?.replacingOccurrences(of: "_", with: " ").capitalized ?? "?"
                return .init(icon: "arrow.right.circle",
                             text: "\(who) moved \(title): \(from) → \(to)",
                             timestamp: date)
            case "assignee_change":
                return .init(icon: "person.circle",
                             text: "\(who) reassigned \(title)",
                             timestamp: date)
            case "deleted":
                return .init(icon: "trash.circle",
                             text: "\(who) deleted \(title)",
                             timestamp: date)
            default:
                return .init(icon: "circle", text: "\(who) \(event) \(title)", timestamp: date)
            }
        case "file_upload":
            let filename = row.string("filename") ?? "a file"
            return .init(icon: "paperclip",
                         text: "\(who) uploaded \(filename)",
                         timestamp: date)
        case "collaborator_added":
            return .init(icon: "person.badge.plus",
                         text: "\(who) was added to the project",
                         timestamp: date)
        default:
            return nil
        }
    }

    /// Toggle sales-pipeline mode for the current project. Persists to
    /// project_data.pipeline_mode (merged server-side) and refreshes the local
    /// project so the kanban board re-renders with sales stages + deal fields.
    func setPipelineMode(_ enabled: Bool) async {
        guard let pid = project?.id else { return }
        do {
            let updated = try await service.setPipelineMode(projectId: pid, enabled: enabled)
            await MainActor.run { self.project = updated }
        } catch {
            await MainActor.run { self.errorMessage = "Failed to update pipeline mode" }
        }
    }

    func loadProject(id: String) async {
        // Switching projects: clear the per-project secondary arrays so the
        // prior project's tasks/files/activity don't leak into the new overview.
        // But paint the project detail INSTANTLY from cache when we have it,
        // so there's no blank-header flash; a fresh copy revalidates below.
        let switchingProjects = project?.id != id
        if switchingProjects {
            await MainActor.run {
                tasks = []
                files = []
                elements = []
                recentActivity = []
                errorMessage = nil
                if let cached = service.cachedProjectDetail(id) {
                    project = cached
                    activeChatId = cached.chats?.first?.id
                    isLoading = false
                } else {
                    isLoading = true
                }
            }
        } else {
            await MainActor.run { isLoading = true; errorMessage = nil }
        }
        do {
            // forceRefresh: always revalidate (and repopulate the cache) so the
            // instant-paint above can never go stale across opens.
            let proj = try await service.getProjectDetail(id: id, forceRefresh: true)
            await MainActor.run {
                project = proj
                // Reset to the new project's first chat (the VM is reused across
                // projects, so a prior activeChatId would otherwise leak in).
                activeChatId = proj.chats?.first?.id
                isLoading = false
            }
            // Prefetch tasks/files/collaborators on every project open,
            // regardless of `project_type`. Earlier the prefetch was gated
            // on `projectType == "collab"`, which left Overview's UP NEXT
            // card stuck on "No open tasks" for projects whose row had a
            // legacy or NULL project_type — even though Kanban renders the
            // same tasks fine via its own .task block. Cost: one GET per
            // surface; server returns empty arrays for project types that
            // have no rows so the payload is zero-bytes.
            //
            // Use Task { } not `async let _ = ...` — `async let` requires
            // an await before scope exit; without it Swift implicitly
            // cancels the child task and the network request never
            // completes.
            Task { await self.loadTasks() }
            Task { await self.loadFiles() }
            Task { await self.loadCollaborators() }
            Task { await self.loadElements() }
        } catch is CancellationError {
            // Rapid project switch cancelled the in-flight load. Don't show
            // a red banner — the new project's .task is already loading.
            await MainActor.run { isLoading = false }
        } catch {
            let nsErr = error as NSError
            if nsErr.domain == NSURLErrorDomain && nsErr.code == NSURLErrorCancelled {
                await MainActor.run { isLoading = false }
                return
            }
            await MainActor.run { errorMessage = error.localizedDescription; isLoading = false }
        }
    }

    /// Refetch project without touching activeChatId or isLoading. Called when
    /// a child chat stream completes and may have mutated sections / posting /
    /// blog data on the server. Using loadProject here would reset activeChatId
    /// and flicker the loading state.
    func refreshProject() async {
        guard let pid = project?.id else { return }
        do {
            let proj = try await service.getProjectDetail(id: pid)
            await MainActor.run { project = proj }
        } catch {
            // Silent — background refresh; don't clobber user-facing errors.
        }
    }

    func addSection(title: String) async {
        guard let pid = project?.id else { return }
        do {
            let updated = try await service.addProjectSection(projectId: pid, title: title)
            await MainActor.run {
                project = updated
                logActivity("text.append", "added section “\(title)”")
            }
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    func updateSection(sectionId: String, title: String? = nil, content: String? = nil) async {
        guard let pid = project?.id else { return }
        do {
            let updated = try await service.updateProjectSection(projectId: pid, sectionId: sectionId, title: title, content: content)
            await MainActor.run { project = updated }
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    func deleteSection(sectionId: String) async {
        guard let pid = project?.id else { return }
        do {
            let updated = try await service.deleteProjectSection(projectId: pid, sectionId: sectionId)
            await MainActor.run { project = updated }
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    func acceptSectionRevision(sectionId: String) async {
        guard let pid = project?.id else { return }
        do {
            let updated = try await service.acceptProjectSectionRevision(projectId: pid, sectionId: sectionId)
            await MainActor.run { project = updated }
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    func rejectSectionRevision(sectionId: String) async {
        guard let pid = project?.id else { return }
        do {
            let updated = try await service.rejectProjectSectionRevision(projectId: pid, sectionId: sectionId)
            await MainActor.run { project = updated }
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    func createChat(title: String?) async {
        guard let pid = project?.id else { return }
        do {
            let thread = try await service.createProjectChat(projectId: pid, title: title)
            await MainActor.run {
                activeChatId = thread.id
            }
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    /// Rename the project. Server returns the updated MWProject; we apply it
    /// directly so the UI reflects the new title without an extra GET.
    /// `updateProjectMeta` invalidates the project list cache, so the sidebar
    /// shows the new title on next render too.
    func updateTitle(_ newTitle: String) async {
        guard let pid = project?.id else { return }
        let trimmed = newTitle.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        // Optimistic — patch the local detail title and tell the sidebar to
        // patch its row in place. Server roundtrip happens after; on failure
        // we revert and re-emit.
        let previous = project?.title
        await MainActor.run {
            project?.title = trimmed
            if let prev = previous, prev != trimmed {
                logActivity("pencil", "renamed to “\(trimmed)”")
            }
        }
        NotificationCenter.default.post(
            name: .mwProjectTitlePatched,
            object: MWProjectTitlePatch(id: pid, title: trimmed)
        )
        do {
            let updated = try await service.updateProjectMeta(id: pid, title: trimmed)
            await MainActor.run { project = updated }
        } catch {
            await MainActor.run {
                if let previous { project?.title = previous }
                errorMessage = error.localizedDescription
            }
            if let previous {
                NotificationCenter.default.post(
                    name: .mwProjectTitlePatched,
                    object: MWProjectTitlePatch(id: pid, title: previous)
                )
            }
        }
    }

    // MARK: - Recruiting

    var recruitingData: MWRecruitingData {
        MWRecruitingData.from(projectData: project?.projectData)
    }

    /// Replace one array key inside the live `project.projectData` blob.
    /// Triggers a reactive re-render via @Observable since `MWRecruitingData`
    /// is recomputed from `projectData` on every access.
    @MainActor
    private func setProjectDataIds(_ key: String, _ ids: [String]) {
        guard var data = project?.projectData else { return }
        data[key] = AnyCodable(ids.map { AnyCodable($0) })
        project?.projectData = data
    }

    func toggleShortlist(candidateId: String) async {
        guard let pid = project?.id else { return }
        let priorIds = recruitingData.shortlistIds
        let wasIn = priorIds.contains(candidateId)
        var next = priorIds
        if wasIn { next.remove(candidateId) } else { next.insert(candidateId) }
        await setProjectDataIds("shortlist_ids", Array(next).sorted())
        do {
            _ = try await service.toggleShortlist(projectId: pid, candidateId: candidateId)
        } catch {
            await setProjectDataIds("shortlist_ids", Array(priorIds).sorted())
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    func toggleDismiss(candidateId: String) async {
        guard let pid = project?.id else { return }
        let priorIds = recruitingData.dismissedIds
        let wasIn = priorIds.contains(candidateId)
        var next = priorIds
        if wasIn { next.remove(candidateId) } else { next.insert(candidateId) }
        await setProjectDataIds("dismissed_ids", Array(next).sorted())
        do {
            _ = try await service.toggleProjectDismiss(projectId: pid, candidateId: candidateId)
        } catch {
            await setProjectDataIds("dismissed_ids", Array(priorIds).sorted())
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    func savePosting(title: String?, content: String, finalized: Bool) async {
        guard let pid = project?.id else { return }
        let payload: [String: Any] = [
            "title": title ?? project?.title ?? "",
            "content": content,
            "finalized": finalized,
        ]
        do {
            _ = try await service.updateProjectPosting(projectId: pid, posting: payload)
            await refreshProject()
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    func uploadProjectResumes(files: [(data: Data, filename: String, mimeType: String)]) async {
        guard let pid = project?.id else { return }
        do {
            let bytes = try await service.uploadProjectResumes(projectId: pid, files: files)
            for try await line in bytes.lines {
                if line.hasPrefix("data: "),
                   line.contains("\"type\":\"complete\"") || line.contains("[DONE]") {
                    break
                }
            }
            await refreshProject()
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    func sendProjectInterviews(candidateIds: [String], positionTitle: String?, customMessage: String?) async {
        guard let pid = project?.id else { return }
        do {
            _ = try await service.sendProjectInterviews(
                projectId: pid,
                candidateIds: candidateIds,
                positionTitle: positionTitle,
                customMessage: customMessage
            )
            await refreshProject()
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    func syncProjectInterviews() async {
        guard let pid = project?.id else { return }
        do {
            try await service.syncProjectInterviews(projectId: pid)
            await refreshProject()
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    func analyzeProjectCandidates() async {
        guard let pid = project?.id else { return }
        do {
            try await service.analyzeProjectCandidates(projectId: pid)
            await refreshProject()
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    func rejectCandidate(candidateId: String, reason: String?, sendEmail: Bool) async {
        guard let pid = project?.id else { return }
        do {
            try await service.rejectProjectCandidate(projectId: pid, candidateId: candidateId, reason: reason, sendEmail: sendEmail)
            await refreshProject()
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    func exportProject(format: String) async -> Data? {
        guard let pid = project?.id else { return nil }
        do {
            return try await service.exportProject(projectId: pid, format: format)
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
            return nil
        }
    }

    // MARK: - Discipline

    func patchDiscipline(_ patch: MatchaWorkService.MWDisciplinePatch) async {
        guard let pid = project?.id else { return }
        do {
            let updated = try await service.patchDiscipline(projectId: pid, patch: patch)
            await MainActor.run { project = updated }
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    func confirmDisciplineMeetingHeld() async {
        guard let pid = project?.id else { return }
        do {
            let updated = try await service.markDisciplineMeetingHeld(projectId: pid)
            await MainActor.run { project = updated }
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    func requestDisciplineSignature(employeeEmail: String) async {
        guard let pid = project?.id else { return }
        do {
            let updated = try await service.requestDisciplineSignature(projectId: pid, employeeEmail: employeeEmail)
            await MainActor.run { project = updated }
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    func refuseDisciplineSignature(notes: String) async {
        guard let pid = project?.id else { return }
        do {
            let updated = try await service.refuseDisciplineSignature(projectId: pid, notes: notes)
            await MainActor.run { project = updated }
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    func uploadDisciplinePhysicalSignature(fileURL: URL) async {
        guard let pid = project?.id else { return }
        do {
            let updated = try await service.uploadDisciplinePhysicalSignature(projectId: pid, fileURL: fileURL)
            await MainActor.run { project = updated }
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    // MARK: - Blog

    var blogData: MWBlogData {
        MWBlogData.from(projectData: project?.projectData)
    }

    func patchBlog(_ patch: MWBlogPatchRequest) async {
        guard let pid = project?.id else { return }
        do {
            let updated = try await service.patchBlog(id: pid, patch: patch)
            await MainActor.run { project = updated }
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    func transitionBlogStatus(to status: String) async {
        guard let pid = project?.id else { return }
        do {
            let updated = try await service.transitionBlogStatus(id: pid, status: status)
            await MainActor.run { project = updated }
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    func exportBlogMarkdown() async -> Data? {
        guard let pid = project?.id else { return nil }
        do {
            return try await service.exportProject(projectId: pid, format: "md_frontmatter")
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
            return nil
        }
    }

    // MARK: - Collab: tasks

    func loadTasks() async {
        guard let pid = project?.id else { return }
        await MainActor.run { isLoadingTasks = true }
        do {
            let list = try await service.listProjectTasks(projectId: pid)
            await MainActor.run {
                tasks = list
                var seeded: [String: [MWProjectFile]] = [:]
                for t in list {
                    if let atts = t.attachments { seeded[t.id] = atts }
                }
                taskFiles = seeded
                isLoadingTasks = false
            }
        } catch is CancellationError {
            // Project switch / re-render race — don't surface as red banner.
            await MainActor.run { isLoadingTasks = false }
        } catch {
            let nsErr = error as NSError
            if nsErr.domain == NSURLErrorDomain && nsErr.code == NSURLErrorCancelled {
                await MainActor.run { isLoadingTasks = false }
                return
            }
            await MainActor.run {
                errorMessage = error.localizedDescription
                isLoadingTasks = false
            }
        }
    }

    func addTask(title: String, column: String = "todo", pipelineColumn: String = "lead", priority: String = "medium", assignedTo: String? = nil, description: String? = nil, category: String? = nil, elementId: String? = nil, subtasks: [String]? = nil) async {
        guard let pid = project?.id else { return }
        do {
            let task = try await service.createProjectTask(
                projectId: pid, title: title,
                boardColumn: column, pipelineColumn: pipelineColumn,
                description: description,
                priority: priority, assignedTo: assignedTo, category: category, elementId: elementId,
                subtasks: subtasks
            )
            await MainActor.run {
                tasks.insert(task, at: 0)
                logActivity("plus.circle", "added task “\(title)”")
            }
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    // MARK: - Collab: realtime task fan-out (project WS task.created/updated/deleted)

    /// Wire the project WS task event callbacks to apply* methods. Call once
    /// per loadProject. `currentUserId` (from AppState) is captured so self-
    /// echoes from our own create / update / delete don't double-apply.
    @MainActor
    func attachTaskRealtime(currentUserId: String?) {
        print("[ProjectVM] attachTaskRealtime user=\(currentUserId ?? "nil")")
        self.currentUserId = currentUserId
        let ws = ProjectWebSocket.shared
        ws.onTaskCreated = { [weak self] dict in
            print("[ProjectVM] onTaskCreated task=\(dict["id"] ?? "?") actor=\(dict["actor_id"] ?? "?")")
            guard let self else { return }
            let actorId = dict["actor_id"] as? String
            if let actorId, actorId == self.currentUserId {
                print("[ProjectVM] onTaskCreated suppressed — self-echo")
                return
            }
            if let task = Self.decodeTask(dict) {
                Task { @MainActor in self.applyTaskCreated(task) }
            }
        }
        ws.onTaskUpdated = { [weak self] dict in
            print("[ProjectVM] onTaskUpdated task=\(dict["id"] ?? "?") actor=\(dict["actor_id"] ?? "?") column=\(dict["board_column"] ?? "?")")
            guard let self else { return }
            if let task = Self.decodeTask(dict) {
                Task { @MainActor in self.applyTaskUpdated(task) }
            }
        }
        ws.onTaskDeleted = { [weak self] taskId, actorId in
            print("[ProjectVM] onTaskDeleted task=\(taskId) actor=\(actorId ?? "?")")
            guard let self else { return }
            if let actorId, actorId == self.currentUserId { return }
            Task { @MainActor in self.applyTaskDeleted(taskId) }
        }
    }

    private static func decodeTask(_ dict: [String: Any]) -> MWProjectTask? {
        guard let data = try? JSONSerialization.data(withJSONObject: dict) else { return nil }
        return try? JSONDecoder().decode(MWProjectTask.self, from: data)
    }

    @MainActor
    private func applyTaskCreated(_ t: MWProjectTask) {
        // Dedupe by id — guards against the post-optimistic-create echo when
        // actor_id was missing for any reason.
        if tasks.contains(where: { $0.id == t.id }) { return }
        tasks.insert(t, at: 0)
        if let atts = t.attachments { taskFiles[t.id] = atts }
    }

    @MainActor
    private func applyTaskUpdated(_ t: MWProjectTask) {
        if tasks.contains(where: { $0.id == t.id }) {
            replacePreservingAggregates(t)
        } else {
            tasks.insert(t, at: 0)
        }
        if let atts = t.attachments { taskFiles[t.id] = atts }
    }

    /// Replace a task in `tasks`, carrying forward the list-only aggregate
    /// fields (review cycle count, subtask progress) when the incoming row
    /// omits them. Single-task responses (move / toggle / edit / reject) and
    /// most WS payloads don't compute these — only the full list query does —
    /// so a naive replace would blink the card's chips/progress out until the
    /// next reload. The reject response *does* carry review_cycle_count, so its
    /// fresh value wins there; nil-guards only fill the gaps.
    @MainActor
    private func replacePreservingAggregates(_ updated: MWProjectTask) {
        guard let i = tasks.firstIndex(where: { $0.id == updated.id }) else { return }
        var merged = updated
        if merged.reviewCycleCount == nil { merged.reviewCycleCount = tasks[i].reviewCycleCount }
        if merged.subtaskTotal == nil { merged.subtaskTotal = tasks[i].subtaskTotal }
        if merged.subtaskDone == nil { merged.subtaskDone = tasks[i].subtaskDone }
        tasks[i] = merged
    }

    @MainActor
    private func applyTaskDeleted(_ id: String) {
        tasks.removeAll { $0.id == id }
        taskFiles.removeValue(forKey: id)
    }

    // MARK: - Collab: task file attachments

    func loadTaskFiles(taskId: String) async {
        guard let pid = project?.id else { return }
        do {
            let list = try await service.listTaskFiles(projectId: pid, taskId: taskId)
            await MainActor.run { taskFiles[taskId] = list }
        } catch is CancellationError {
            return
        } catch {
            let nsErr = error as NSError
            if nsErr.domain == NSURLErrorDomain && nsErr.code == NSURLErrorCancelled { return }
        }
    }

    func uploadTaskFile(taskId: String, data: Data, filename: String, mimeType: String) async {
        guard let pid = project?.id else { return }
        do {
            let uploaded = try await service.uploadTaskFile(
                projectId: pid, taskId: taskId,
                file: (data: data, filename: filename, mimeType: mimeType)
            )
            await MainActor.run {
                var existing = taskFiles[taskId] ?? []
                existing.insert(uploaded, at: 0)
                taskFiles[taskId] = existing
                logActivity("paperclip", "attached \(filename)")
            }
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    func deleteTaskFile(taskId: String, fileId: String) async {
        guard let pid = project?.id else { return }
        let snapshot = taskFiles[taskId]
        await MainActor.run {
            taskFiles[taskId] = (taskFiles[taskId] ?? []).filter { $0.id != fileId }
        }
        do {
            try await service.deleteTaskFile(projectId: pid, taskId: taskId, fileId: fileId)
        } catch {
            await MainActor.run {
                if let snap = snapshot { taskFiles[taskId] = snap }
                errorMessage = error.localizedDescription
            }
        }
    }

    // MARK: - Collab: task subtasks (checklist)

    func loadSubtasks(taskId: String) async {
        guard let pid = project?.id else { return }
        do {
            let list = try await service.listSubtasks(projectId: pid, taskId: taskId)
            await MainActor.run {
                taskSubtasks[taskId] = list
                syncSubtaskCounts(taskId: taskId)
            }
        } catch is CancellationError {
            return
        } catch {
            let nsErr = error as NSError
            if nsErr.domain == NSURLErrorDomain && nsErr.code == NSURLErrorCancelled { return }
        }
    }

    func addSubtask(taskId: String, title: String) async {
        guard let pid = project?.id else { return }
        let trimmed = title.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        do {
            let created = try await service.createSubtask(projectId: pid, taskId: taskId, title: trimmed)
            await MainActor.run {
                var existing = taskSubtasks[taskId] ?? []
                existing.append(created)
                taskSubtasks[taskId] = existing
                syncSubtaskCounts(taskId: taskId)
            }
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    func toggleSubtask(taskId: String, subtaskId: String, isDone: Bool) async {
        guard let pid = project?.id else { return }
        // Optimistic flip so the checkbox feels instant.
        await MainActor.run {
            if var list = taskSubtasks[taskId],
               let i = list.firstIndex(where: { $0.id == subtaskId }) {
                list[i].isDone = isDone
                taskSubtasks[taskId] = list
                syncSubtaskCounts(taskId: taskId)
            }
        }
        do {
            let updated = try await service.setSubtaskDone(
                projectId: pid, taskId: taskId, subtaskId: subtaskId, isDone: isDone
            )
            await MainActor.run {
                if var list = taskSubtasks[taskId],
                   let i = list.firstIndex(where: { $0.id == subtaskId }) {
                    list[i] = updated
                    taskSubtasks[taskId] = list
                    syncSubtaskCounts(taskId: taskId)
                }
            }
        } catch {
            await MainActor.run {
                // Revert the optimistic flip on failure.
                if var list = taskSubtasks[taskId],
                   let i = list.firstIndex(where: { $0.id == subtaskId }) {
                    list[i].isDone = !isDone
                    taskSubtasks[taskId] = list
                    syncSubtaskCounts(taskId: taskId)
                }
                errorMessage = error.localizedDescription
            }
        }
    }

    func deleteSubtask(taskId: String, subtaskId: String) async {
        guard let pid = project?.id else { return }
        let snapshot = taskSubtasks[taskId]
        await MainActor.run {
            taskSubtasks[taskId] = (taskSubtasks[taskId] ?? []).filter { $0.id != subtaskId }
            syncSubtaskCounts(taskId: taskId)
        }
        do {
            try await service.deleteSubtask(projectId: pid, taskId: taskId, subtaskId: subtaskId)
        } catch {
            await MainActor.run {
                if let snap = snapshot { taskSubtasks[taskId] = snap }
                syncSubtaskCounts(taskId: taskId)
                errorMessage = error.localizedDescription
            }
        }
    }

    /// Mirror the cached checklist's counts onto the matching `tasks` entry so
    /// the kanban card's "done/total" updates immediately, without a reload.
    @MainActor
    private func syncSubtaskCounts(taskId: String) {
        guard let list = taskSubtasks[taskId],
              let i = tasks.firstIndex(where: { $0.id == taskId }) else { return }
        tasks[i].subtaskTotal = list.count
        tasks[i].subtaskDone = list.filter { $0.isDone }.count
    }

    func loadCollaborators() async {
        guard let pid = project?.id else { return }
        do {
            let list = try await service.listCollaborators(projectId: pid)
            await MainActor.run { collaborators = list }
        } catch is CancellationError {
            return
        } catch {
            let nsErr = error as NSError
            if nsErr.domain == NSURLErrorDomain && nsErr.code == NSURLErrorCancelled {
                return
            }
            // Silent — picker just shows "Unassigned"; don't red-banner.
        }
    }

    // MARK: - Elements

    func loadElements() async {
        guard let pid = project?.id else { return }
        do {
            let list = try await service.listProjectElements(projectId: pid)
            await MainActor.run { elements = list }
        } catch is CancellationError { return
        } catch {
            let nsErr = error as NSError
            if nsErr.domain == NSURLErrorDomain && nsErr.code == NSURLErrorCancelled { return }
        }
    }

    @discardableResult
    func createElement(name: String, kind: String?, description: String?, assignedTo: String?) async -> MWProjectElement? {
        guard let pid = project?.id else { return nil }
        do {
            let el = try await service.createProjectElement(
                projectId: pid, name: name, kind: kind,
                description: description, assignedTo: assignedTo
            )
            await MainActor.run { elements.append(el) }
            return el
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
            return nil
        }
    }

    func updateElement(_ element: MWProjectElement, name: String?, kind: String?, description: String?, assignedTo: String?) async {
        guard let pid = project?.id else { return }
        do {
            let updated = try await service.updateProjectElement(
                projectId: pid, elementId: element.id,
                name: name, kind: kind,
                description: description, assignedTo: assignedTo
            )
            await MainActor.run {
                if let i = elements.firstIndex(where: { $0.id == element.id }) {
                    elements[i] = updated
                }
            }
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    func deleteElement(_ element: MWProjectElement) async {
        guard let pid = project?.id else { return }
        await MainActor.run { elements.removeAll { $0.id == element.id } }
        do {
            try await service.deleteProjectElement(projectId: pid, elementId: element.id)
        } catch {
            await loadElements()
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    func moveTask(id: String, toColumn column: String) async {
        guard let pid = project?.id else { return }
        // Optimistic update
        await MainActor.run {
            if let idx = tasks.firstIndex(where: { $0.id == id }) {
                tasks[idx].boardColumn = column
                if column == "done" {
                    tasks[idx].status = "completed"
                } else if tasks[idx].status == "completed" {
                    tasks[idx].status = "pending"
                }
            }
        }
        do {
            let updated = try await service.updateProjectTask(
                projectId: pid, taskId: id,
                patch: MatchaWorkService.ProjectTaskPatch(boardColumn: column)
            )
            await MainActor.run { replacePreservingAggregates(updated) }
        } catch {
            await loadTasks()
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    func movePipelineTask(id: String, toStage stage: String) async {
        guard let pid = project?.id else { return }
        await MainActor.run {
            if let idx = tasks.firstIndex(where: { $0.id == id }) {
                tasks[idx].pipelineColumn = stage
            }
        }
        do {
            let updated = try await service.updateProjectTask(
                projectId: pid, taskId: id,
                patch: MatchaWorkService.ProjectTaskPatch(pipelineColumn: stage)
            )
            await MainActor.run { replacePreservingAggregates(updated) }
        } catch {
            await loadTasks()
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    func toggleTaskComplete(id: String) async {
        guard let pid = project?.id else { return }
        guard let idx = tasks.firstIndex(where: { $0.id == id }) else { return }
        let newStatus = tasks[idx].status == "completed" ? "pending" : "completed"
        let newColumn = newStatus == "completed" ? "done" : "todo"
        let title = tasks[idx].title
        await MainActor.run {
            // Replace the whole element (rather than mutating two fields in
            // sequence) so SwiftUI sees a single coherent change and the row
            // animates cleanly between columns.
            var copy = tasks[idx]
            copy.status = newStatus
            copy.boardColumn = newColumn
            tasks[idx] = copy
            if newStatus == "completed" {
                logActivity("checkmark.circle.fill", "completed “\(title)”")
            } else {
                logActivity("arrow.uturn.left", "reopened “\(title)”")
            }
        }
        do {
            // Send both status AND board_column. The server enforces sync
            // rules either way, but sending both makes intent explicit and
            // protects against a server that returns the row before the
            // column-sync rule has applied (which would snap the card back).
            let updated = try await service.updateProjectTask(
                projectId: pid, taskId: id,
                patch: MatchaWorkService.ProjectTaskPatch(
                    boardColumn: newColumn,
                    status: newStatus
                )
            )
            await MainActor.run {
                if tasks.contains(where: { $0.id == id }) {
                    // Defensive: if the server response somehow diverges from
                    // the intended state, normalize it client-side. The
                    // status↔column relationship is invariant.
                    var fixed = updated
                    if fixed.status == "completed" && fixed.boardColumn != "done" {
                        fixed.boardColumn = "done"
                    } else if fixed.status == "pending" && fixed.boardColumn == "done" {
                        fixed.boardColumn = "todo"
                    }
                    replacePreservingAggregates(fixed)
                }
            }
        } catch {
            print("[Kanban] toggleTaskComplete PATCH failed task=\(id): \(error)")
            await loadTasks()
            await MainActor.run { errorMessage = "Toggle failed: \(error.localizedDescription)" }
        }
    }

    func updateTask(id: String, patch: MatchaWorkService.ProjectTaskPatch) async {
        guard let pid = project?.id else { return }
        do {
            let updated = try await service.updateProjectTask(projectId: pid, taskId: id, patch: patch)
            await MainActor.run { replacePreservingAggregates(updated) }
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    /// Reviewer sends a task back for changes — bounces it to the
    /// changes_requested lane with a note and emails the assignee (server-side).
    /// Returns true on success.
    @discardableResult
    func rejectTask(id: String, note: String) async -> Bool {
        guard let pid = project?.id else { return false }
        do {
            let updated = try await service.rejectTask(projectId: pid, taskId: id, note: note)
            await MainActor.run {
                replacePreservingAggregates(updated)
                logActivity("arrow.uturn.backward", "sent “\(updated.title)” back for changes")
            }
            return true
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
            return false
        }
    }

    func deleteTask(id: String) async {
        guard let pid = project?.id else { return }
        await MainActor.run { tasks.removeAll { $0.id == id } }
        do {
            try await service.deleteProjectTask(projectId: pid, taskId: id)
        } catch {
            await loadTasks()
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    func markProjectComplete() async {
        guard let pid = project?.id else { return }
        let previousStatus = project?.status
        await MainActor.run { project?.status = "completed" }
        do {
            try await service.markProjectComplete(projectId: pid)
            await refreshProject()
        } catch {
            await MainActor.run {
                project?.status = previousStatus
                errorMessage = error.localizedDescription
            }
        }
    }

    // MARK: - Collab: files

    func loadFiles() async {
        guard let pid = project?.id else { return }
        await MainActor.run { isLoadingFiles = true }
        do {
            // Files + folders concurrently (was serial → doubled the latency).
            async let filesReq = service.listProjectFiles(projectId: pid)
            async let foldersReq = service.listProjectFolders(projectId: pid)
            let list = try await filesReq
            let fetchedFolders = try? await foldersReq
            await MainActor.run {
                files = list
                if let fetchedFolders { folders = fetchedFolders }
                isLoadingFiles = false
            }
        } catch is CancellationError {
            await MainActor.run { isLoadingFiles = false }
        } catch {
            let nsErr = error as NSError
            if nsErr.domain == NSURLErrorDomain && nsErr.code == NSURLErrorCancelled {
                await MainActor.run { isLoadingFiles = false }
                return
            }
            await MainActor.run {
                errorMessage = error.localizedDescription
                isLoadingFiles = false
            }
        }
    }

    /// Backfill Files/Media with chat attachments (screenshots dropped in chat),
    /// then reload if anything was added. Idempotent + best-effort.
    func syncChatFiles() async {
        guard let pid = project?.id else { return }
        if let added = try? await service.syncChatFiles(projectId: pid), added > 0 {
            await loadFiles()
        }
    }

    /// Links shared in the collab chat (URLs parsed from messages). Best-effort:
    /// failures leave the previous list intact rather than surfacing an error.
    func loadLinks() async {
        guard let pid = project?.id else { return }
        if let list = try? await service.listProjectLinks(projectId: pid) {
            await MainActor.run { links = list }
        }
    }

    func uploadFile(data: Data, filename: String, mimeType: String) async {
        guard let pid = project?.id else { return }
        do {
            let uploaded = try await service.uploadProjectFile(
                projectId: pid, file: (data: data, filename: filename, mimeType: mimeType)
            )
            await MainActor.run {
                files.insert(uploaded, at: 0)
                logActivity("doc.fill", "uploaded \(filename)")
            }
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    func uploadFile(data: Data, filename: String, mimeType: String, folderId: String) async {
        let countBefore = files.count
        await uploadFile(data: data, filename: filename, mimeType: mimeType)
        guard files.count > countBefore,
              let file = files.first(where: { $0.folderId == nil && $0.filename == filename })
        else { return }
        await moveFile(id: file.id, toFolder: folderId)
    }

    func deleteFile(id: String) async {
        guard let pid = project?.id else { return }
        await MainActor.run { files.removeAll { $0.id == id } }
        do {
            try await service.deleteProjectFile(projectId: pid, fileId: id)
        } catch {
            await loadFiles()
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    // MARK: - Collab: file folders

    func loadFolders() async {
        guard let pid = project?.id else { return }
        if let list = try? await service.listProjectFolders(projectId: pid) {
            await MainActor.run { folders = list }
        }
    }

    @discardableResult
    func createFolder(name: String, parentId: String? = nil) async -> MWProjectFolder? {
        guard let pid = project?.id else { return nil }
        let clean = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !clean.isEmpty else { return nil }
        do {
            let folder = try await service.createProjectFolder(projectId: pid, name: clean, parentId: parentId)
            await MainActor.run {
                folders.append(folder)
                folders.sort { $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending }
            }
            return folder
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
            return nil
        }
    }

    func renameFolder(id: String, name: String) async {
        guard let pid = project?.id else { return }
        let clean = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !clean.isEmpty else { return }
        do {
            let updated = try await service.renameProjectFolder(projectId: pid, folderId: id, name: clean)
            await MainActor.run {
                if let idx = folders.firstIndex(where: { $0.id == id }) { folders[idx] = updated }
            }
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    func deleteFolder(id: String) async {
        guard let pid = project?.id else { return }
        await MainActor.run {
            folders.removeAll { $0.id == id }
            // Files in the deleted folder fall back to the root (matches the
            // backend's ON DELETE SET NULL).
            for i in files.indices where files[i].folderId == id { files[i].folderId = nil }
        }
        do {
            try await service.deleteProjectFolder(projectId: pid, folderId: id)
        } catch {
            await loadFiles()
            await loadFolders()
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    /// Move a file into a folder, or to the root when folderId is nil.
    func moveFile(id: String, toFolder folderId: String?) async {
        guard let pid = project?.id else { return }
        await MainActor.run {
            if let idx = files.firstIndex(where: { $0.id == id }) { files[idx].folderId = folderId }
        }
        do {
            _ = try await service.moveProjectFile(projectId: pid, fileId: id, folderId: folderId)
        } catch {
            await loadFiles()
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    /// Copy a file into a folder, leaving the original at root. The original
    /// keeps `folderId == nil` (stays in Media); the returned copy carries the
    /// folderId (shows in the Files tab under that folder).
    func copyFileToFolder(id: String, toFolder folderId: String) async {
        guard let pid = project?.id else { return }
        do {
            let copy = try await service.copyProjectFile(projectId: pid, fileId: id, folderId: folderId)
            await MainActor.run {
                if !files.contains(where: { $0.id == copy.id }) { files.insert(copy, at: 0) }
            }
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }
}

// MARK: - Export save panel (free function so ProjectDetailView.swift stays short)

@MainActor
func presentExportSavePanel(data: Data, format: String, title: String) {
    let panel = NSSavePanel()
    panel.nameFieldStringValue = "\(title).\(format)"
    switch format {
    case "pdf":
        panel.allowedContentTypes = [.pdf]
    case "docx":
        if let t = UTType(filenameExtension: "docx") { panel.allowedContentTypes = [t] }
    case "md":
        if let t = UTType(filenameExtension: "md") { panel.allowedContentTypes = [t] }
    default:
        break
    }
    Task {
        let response: NSApplication.ModalResponse
        if let window = NSApp.keyWindow ?? NSApp.mainWindow {
            response = await panel.beginSheetModal(for: window)
        } else {
            response = await panel.begin()
        }
        guard response == .OK, let url = panel.url else { return }
        do {
            try data.write(to: url)
        } catch {
            print("[Export] write failed: \(error)")
        }
    }
}

