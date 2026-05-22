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
    var isLoadingFiles = false
    var collaborators: [MWProjectCollaborator] = []
    var elements: [MWProjectElement] = []
    /// Attachments per task, keyed by task id. Seeded by `loadTasks`
    /// (server embeds `attachments` per task) and updated by add/delete.
    var taskFiles: [String: [MWProjectFile]] = [:]
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
        // Clear per-project caches before fetching. The VM is persistent
        // @State on ProjectDetailView and gets reused across projects, so
        // without this reset Project A's tasks/files/activity render in
        // Project B's overview during the gap between project switch and
        // loadTasks/loadFiles completing.
        let switchingProjects = project?.id != id
        if switchingProjects {
            await MainActor.run {
                tasks = []
                files = []
                elements = []
                recentActivity = []
            }
        }
        await MainActor.run { isLoading = true; errorMessage = nil }
        do {
            let proj = try await service.getProjectDetail(id: id)
            await MainActor.run {
                project = proj
                // Always pick up the loaded project's first chat. The VM is
                // persistent @State on ProjectDetailView, so switching to a
                // different project (or creating a new one) reuses the same
                // instance. Without this reset, activeChatId from the previous
                // project leaks in, and chatVM renders the old project's
                // chat in the new project's editor.
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

    func addTask(title: String, column: String = "todo", priority: String = "medium", assignedTo: String? = nil, description: String? = nil, category: String? = nil, elementId: String? = nil) async {
        guard let pid = project?.id else { return }
        do {
            let task = try await service.createProjectTask(
                projectId: pid, title: title, boardColumn: column, description: description,
                priority: priority, assignedTo: assignedTo, category: category, elementId: elementId
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
        if let i = tasks.firstIndex(where: { $0.id == t.id }) {
            tasks[i] = t
        } else {
            tasks.insert(t, at: 0)
        }
        if let atts = t.attachments { taskFiles[t.id] = atts }
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
            await MainActor.run {
                if let idx = tasks.firstIndex(where: { $0.id == id }) {
                    tasks[idx] = updated
                }
            }
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
                if let i = tasks.firstIndex(where: { $0.id == id }) {
                    // Defensive: if the server response somehow diverges from
                    // the intended state, normalize it client-side. The
                    // status↔column relationship is invariant.
                    var fixed = updated
                    if fixed.status == "completed" && fixed.boardColumn != "done" {
                        fixed.boardColumn = "done"
                    } else if fixed.status == "pending" && fixed.boardColumn == "done" {
                        fixed.boardColumn = "todo"
                    }
                    tasks[i] = fixed
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
            await MainActor.run {
                if let i = tasks.firstIndex(where: { $0.id == id }) {
                    tasks[i] = updated
                }
            }
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
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
            let list = try await service.listProjectFiles(projectId: pid)
            await MainActor.run {
                files = list
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

