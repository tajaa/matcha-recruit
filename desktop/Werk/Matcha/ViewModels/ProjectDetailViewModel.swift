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
    var tasks: [MWProjectTask] = [] {
        didSet { tasksVersion &+= 1 }   // invalidates the grouped-column cache
    }
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
    /// Pending commit→subtask suggestions for the current project, keyed by
    /// task id. Filled by `scanCommits()` / `loadCommitSuggestions()`; the
    /// TaskViewer checklist renders a chip per matching subtask.
    var commitSuggestions: [String: [MWCommitSuggestion]] = [:]
    var isScanningCommits = false
    /// One-line result of the last scan ("3 commits · 2 suggestions"), shown
    /// transiently in the Elements header.
    var lastScanSummary: String?
    /// Repo-snapshot sync (uploads element code text for Prop grounding).
    var isSyncingRepo = false
    var lastSyncSummary: String?
    /// Per-project last auto-sync time → cooldown so opening the Props tab
    /// repeatedly never spams GitHub. In-memory on the (cached) VM, so it
    /// survives tab switches. Manual Sync bypasses it.
    private var lastGitHubSyncAt: [String: Date] = [:]
    /// Per-project last commit-scan time → cooldown for auto-scan on Kanban open.
    private var lastGitHubScanAt: [String: Date] = [:]
    private let githubSyncCooldown: TimeInterval = 600  // 10 min
    /// Per-session activity log surfaced in the collab Overview panel. Capped
    /// at 20 entries; FIFO eviction. In-memory only — survives panel switches
    /// but not project switches or app relaunches. Backend feed is a follow-up.
    var recentActivity: [CollabActivityItem] = []

    private let service = MatchaWorkService.shared
    // Per-project "last fetched" stamps so a tab re-entry within 30s is a no-op:
    // the per-entity service cache + these in-memory arrays are already fresh,
    // and the project WS pushes task deltas live. Keyed by projectId.
    private var lastFilesFetch: [String: Date] = [:]
    private var lastLinksFetch: [String: Date] = [:]
    private var lastChatSyncFetch: [String: Date] = [:]
    private func isFresh(_ map: [String: Date], _ pid: String, within: TimeInterval = 30) -> Bool {
        if let t = map[pid] { return Date().timeIntervalSince(t) < within }
        return false
    }
    /// Logged-in user — used to suppress self-echoes from the project WS
    /// task event fan-out (we already applied the change optimistically).
    var currentUserId: String?

    // ── Grouped-column cache ──────────────────────────────────────────────
    // The kanban board's `columnView` lives inside a GeometryReader that
    // re-evaluates every frame during a window-resize drag. Filtering, sorting,
    // and ISO-date-parsing the task list per column per frame pinned resize to
    // ~11fps. `groupedColumns` memoizes the fully-ordered per-column arrays and
    // only recomputes when (tasks, search, mode) actually change — a resize is
    // a cache hit. `@ObservationIgnored` so writing the cache during view-body
    // evaluation neither triggers observation nor trips "modifying state during
    // view update".
    @ObservationIgnored private var tasksVersion = 0
    @ObservationIgnored private var groupKey: (v: Int, pipeline: Bool, search: String)?
    @ObservationIgnored private var groupValue: [String: [MWProjectTask]] = [:]

    /// Tasks grouped by board/pipeline column key, each bucket in final display
    /// order (priority desc, then oldest-waiting first; the `done` bucket is
    /// pre-sorted most-recently-completed first). Tasks whose column isn't a
    /// known key fall into the first column. Memoized — see the note above.
    func groupedColumns(pipeline: Bool, search: String) -> [String: [MWProjectTask]] {
        if let k = groupKey, k.v == tasksVersion, k.pipeline == pipeline, k.search == search {
            return groupValue
        }
        let cols = pipeline ? SalesStage.columns : kanbanColumns
        let colKeys = Set(cols.map { $0.key })
        let firstKey = cols.first?.key
        let tokens = KanbanSearch.tokens(search)

        // Parse each task's createdAt exactly once (vs. twice per comparison in
        // an O(n log n) sort).
        var created: [String: Date] = [:]
        created.reserveCapacity(tasks.count)
        for t in tasks { created[t.id] = PacificDateFormatter.parse(t.createdAt) ?? .distantFuture }

        var out: [String: [MWProjectTask]] = [:]
        for t in tasks where KanbanSearch.matches(t, tokens: tokens) {
            let raw = pipeline ? (t.pipelineColumn ?? "lead") : t.boardColumn
            let key = colKeys.contains(raw) ? raw : (firstKey ?? raw)
            out[key, default: []].append(t)
        }
        for (k, bucket) in out {
            out[k] = bucket.sorted {
                // Seriousness dictates order: critical → high → medium → low.
                // Secondary: oldest-waiting first within a priority bucket, so
                // the longest-pending (and reddest) card floats to the top.
                if $0.priorityRank != $1.priorityRank { return $0.priorityRank < $1.priorityRank }
                return (created[$0.id] ?? .distantFuture) < (created[$1.id] ?? .distantFuture)
            }
        }
        // Done column collapses to the 5 most-recently-completed (newest first);
        // sort that bucket by completion instead of the priority/age order.
        if !pipeline, var done = out["done"] {
            done.sort {
                (PacificDateFormatter.parse($0.completedAt ?? $0.updatedAt ?? $0.createdAt) ?? .distantPast)
                > (PacificDateFormatter.parse($1.completedAt ?? $1.updatedAt ?? $1.createdAt) ?? .distantPast)
            }
            out["done"] = done
        }

        groupKey = (tasksVersion, pipeline, search)
        groupValue = out
        return out
    }

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

    /// Change the project's sidebar/header icon (SF Symbol name). Optimistic:
    /// paints the new icon immediately; on failure surfaces an error and the
    /// next project load revalidates from the server.
    func setProjectIcon(_ icon: String) async {
        guard let pid = project?.id else { return }
        await MainActor.run { project?.icon = icon }
        do {
            _ = try await service.updateProjectMeta(id: pid, icon: icon)
        } catch {
            await MainActor.run { errorMessage = "Failed to update icon" }
        }
    }

    func loadProject(id: String) async {
        // Stale-while-revalidate. Switching projects paints EVERY surface
        // (header + tasks/files/folders/links/collaborators/elements) instantly
        // from the per-entity service cache instead of blanking the tabs, then
        // revalidates in the background. A cold open (no cache) does a single
        // /bundle round-trip rather than ~6 separate GETs.
        let switchingProjects = project?.id != id
        let cachedDetail = service.cachedProjectDetail(id)
        if switchingProjects {
            await MainActor.run {
                errorMessage = nil
                // Paint per-entity caches if present; cold => empty until the
                // bundle/loaders land below (never leak the prior project's data).
                tasks = service.cachedProjectTasks(id) ?? []
                files = service.cachedProjectFiles(id) ?? []
                folders = service.cachedProjectFolders(id) ?? []
                links = service.cachedProjectLinks(id) ?? []
                collaborators = service.cachedCollaborators(id) ?? []
                elements = service.cachedProjectElements(id) ?? []
                // taskFiles re-seeds from each task's embedded attachments below;
                // clear the prior project's map so ids don't bleed across projects.
                taskFiles = [:]
                recentActivity = []   // Overview's .task(id:) reloads the server feed
                if let cachedDetail {
                    project = cachedDetail
                    activeChatId = cachedDetail.chats?.first?.id
                    isLoading = false
                } else {
                    project = nil      // keeps projectLoadingView until detail lands
                    isLoading = true
                }
            }
        } else {
            await MainActor.run { isLoading = true; errorMessage = nil }
        }
        do {
            if cachedDetail != nil {
                // WARM: header already painted; revalidate detail + every entity
                // in the background (the loaders force-refresh + diff-update).
                let proj = try await service.getProjectDetail(id: id, forceRefresh: true)
                await MainActor.run {
                    guard project?.id == id else { return }
                    project = proj
                    activeChatId = proj.chats?.first?.id
                    isLoading = false
                }
                Task { await self.loadTasks() }
                Task { await self.loadFiles() }
                Task { await self.loadCollaborators() }
                Task { await self.loadElements() }
            } else {
                // COLD: one /bundle call warms detail + all six sub-resources.
                // Fall back to the pre-bundle path (detail + parallel loaders) if
                // the endpoint is unavailable (older server) or fails.
                var bundle: MWProjectBundle?
                do {
                    bundle = try await service.getProjectBundle(id: id)
                } catch is CancellationError {
                    await MainActor.run { isLoading = false }
                    return
                } catch {
                    bundle = nil
                }
                if let bundle {
                    await MainActor.run {
                        project = bundle.project
                        activeChatId = bundle.project.chats?.first?.id
                        tasks = bundle.tasks
                        var seeded: [String: [MWProjectFile]] = [:]
                        for t in bundle.tasks { if let atts = t.attachments { seeded[t.id] = atts } }
                        taskFiles = seeded
                        files = bundle.files
                        folders = bundle.folders
                        links = bundle.links
                        collaborators = bundle.collaborators
                        elements = bundle.elements
                        // Bundle already returned files+folders+links fresh — stamp
                        // so the first Files/Media open doesn't redundantly refetch
                        // (chat-sync is left unstamped so Media still backfills once).
                        lastFilesFetch[id] = Date()
                        lastLinksFetch[id] = Date()
                        isLoading = false
                    }
                } else {
                    let proj = try await service.getProjectDetail(id: id, forceRefresh: true)
                    await MainActor.run {
                        project = proj
                        activeChatId = proj.chats?.first?.id
                        isLoading = false
                    }
                    Task { await self.loadTasks() }
                    Task { await self.loadFiles() }
                    Task { await self.loadCollaborators() }
                    Task { await self.loadElements() }
                }
            }
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
        // Only show the spinner on a cold load; a warm revalidate diff-updates
        // in place so there's no flicker. forceRefresh: this IS the revalidate
        // half of SWR (the cache was already painted by loadProject).
        let wasEmpty = tasks.isEmpty
        await MainActor.run { if wasEmpty { isLoadingTasks = true } }
        do {
            let list = try await service.listProjectTasks(projectId: pid, forceRefresh: true)
            await MainActor.run {
                guard project?.id == pid else { return }   // ignore late landing after a switch
                tasks = list
                var seeded: [String: [MWProjectFile]] = [:]
                for t in list {
                    if let atts = t.attachments { seeded[t.id] = atts }
                    // Seed the unviewed-updates baseline so a ticket's existing
                    // history isn't flagged as new on first sight (we have
                    // recentEventIds here, at the board level).
                    TicketUpdatesStore.shared.baselineIfNeeded(t)
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

    func addTask(title: String, column: String = "todo", pipelineColumn: String = "lead", priority: String = "medium", assignedTo: String? = nil, description: String? = nil, category: String? = nil, elementId: String? = nil, subtasks: [String]? = nil,
                 dealValue: Double? = nil, probability: Int? = nil,
                 contactName: String? = nil, contactCompany: String? = nil,
                 contactEmail: String? = nil, contactPhone: String? = nil,
                 outcome: String? = nil, lossReason: String? = nil,
                 nextActionAt: String? = nil, expectedClose: String? = nil) async {
        guard let pid = project?.id else { return }
        // A deal (sales-pipeline create) carries any deal field — used for the
        // activity-log verb so the timeline reads "added deal" not "added task".
        let isDeal = category == "sales" || dealValue != nil || contactCompany != nil || contactName != nil
        do {
            let task = try await service.createProjectTask(
                projectId: pid, title: title,
                boardColumn: column, pipelineColumn: pipelineColumn,
                description: description,
                priority: priority, assignedTo: assignedTo, category: category, elementId: elementId,
                dealValue: dealValue, probability: probability,
                contactName: contactName, contactCompany: contactCompany,
                contactEmail: contactEmail, contactPhone: contactPhone,
                outcome: outcome, lossReason: lossReason,
                nextActionAt: nextActionAt, expectedClose: expectedClose,
                subtasks: subtasks
            )
            await MainActor.run {
                tasks.insert(task, at: 0)
                logActivity("plus.circle", isDeal ? "added deal “\(title)”" : "added task “\(title)”")
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
                Task { @MainActor in
                    self.applyTaskCreated(task)
                    self.pushTaskToast(actorId: actorId, action: "added", title: task.title,
                                       systemImage: "plus.rectangle.on.rectangle")
                }
            }
        }
        ws.onTaskUpdated = { [weak self] dict in
            print("[ProjectVM] onTaskUpdated task=\(dict["id"] ?? "?") actor=\(dict["actor_id"] ?? "?") column=\(dict["board_column"] ?? "?")")
            guard let self else { return }
            let actorId = dict["actor_id"] as? String
            if let task = Self.decodeTask(dict) {
                Task { @MainActor in
                    // Capture the prior column before applying so we can tell a
                    // lane move from an in-place edit for the toast copy.
                    let prevColumn = self.tasks.first(where: { $0.id == task.id })?.boardColumn
                    self.applyTaskUpdated(task)
                    if actorId != self.currentUserId {
                        if let prevColumn, prevColumn != task.boardColumn {
                            let label = kanbanColumns.first(where: { $0.key == task.boardColumn })?.label ?? task.boardColumn
                            self.pushTaskToast(actorId: actorId, action: "moved", title: task.title,
                                               suffix: "to \(label)", systemImage: "arrow.left.arrow.right")
                        } else {
                            self.pushTaskToast(actorId: actorId, action: "updated", title: task.title,
                                               systemImage: "pencil")
                        }
                    }
                }
            }
        }
        ws.onTaskDeleted = { [weak self] taskId, actorId in
            print("[ProjectVM] onTaskDeleted task=\(taskId) actor=\(actorId ?? "?")")
            guard let self else { return }
            if let actorId, actorId == self.currentUserId { return }
            Task { @MainActor in
                let title = self.tasks.first(where: { $0.id == taskId })?.title
                self.applyTaskDeleted(taskId)
                self.pushTaskToast(actorId: actorId, action: "removed", title: title,
                                   systemImage: "trash")
            }
        }
    }

    /// Resolve a collaborator's display name from the loaded project roster.
    private func collaboratorName(_ id: String?) -> String {
        guard let id else { return "A collaborator" }
        return project?.collaborators?.first(where: { $0.userId == id })?.name ?? "A collaborator"
    }

    /// Push an in-app toast for a collaborator's ticket change so the user gets
    /// a real-time nudge even when they're not looking at the board. Tapping it
    /// jumps to the project. No-op if the project isn't loaded.
    @MainActor
    private func pushTaskToast(actorId: String?, action: String, title: String?,
                               suffix: String? = nil, systemImage: String) {
        guard let proj = project else { return }
        let who = collaboratorName(actorId)
        var msg: String
        if let title, !title.isEmpty {
            msg = "\(who) \(action) \u{201C}\(title)\u{201D}"
        } else {
            msg = "\(who) \(action) a ticket"
        }
        if let suffix, !suffix.isEmpty { msg += " \(suffix)" }
        WorkToastCenter.shared.push(
            WorkToastCenter.Toast(
                projectId: proj.id,
                projectTitle: proj.title,
                message: msg,
                systemImage: systemImage
            )
        )
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
        if merged.updateCount == nil { merged.updateCount = tasks[i].updateCount }
        if merged.recentEventIds == nil { merged.recentEventIds = tasks[i].recentEventIds }
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

    /// Returns the uploaded file's id on success, nil on failure. The id lets
    /// the note composer link a freshly-uploaded screenshot to the note it's
    /// being submitted with (`logTaskActivity(attachmentIds:)`).
    @discardableResult
    func uploadTaskFile(taskId: String, data: Data, filename: String, mimeType: String) async -> String? {
        guard let pid = project?.id else { return nil }
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
            return uploaded.id
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
            return nil
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

    /// Assign or unassign a subtask (pass nil to clear). Replaces the cached
    /// row with the server's response on success.
    func assignSubtask(taskId: String, subtaskId: String, assignedTo: String?) async {
        guard let pid = project?.id else { return }
        do {
            let updated = try await service.setSubtaskAssignee(
                projectId: pid, taskId: taskId, subtaskId: subtaskId, assignedTo: assignedTo
            )
            await MainActor.run {
                if var list = taskSubtasks[taskId],
                   let i = list.firstIndex(where: { $0.id == subtaskId }) {
                    list[i] = updated
                    taskSubtasks[taskId] = list
                }
            }
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    /// Mirror the cached checklist's counts onto the matching `tasks` entry so
    /// the kanban card's "done/total" updates immediately, without a reload.
    @MainActor
    private func syncSubtaskCounts(taskId: String) {
        guard let list = taskSubtasks[taskId],
              let i = tasks.firstIndex(where: { $0.id == taskId }) else { return }
        // Scope to the current round (max round_index) so the card face matches
        // the live checklist — past-round items are archived, not counted.
        let current = list.map { $0.roundIndex ?? 1 }.max() ?? 1
        let scoped = list.filter { ($0.roundIndex ?? 1) == current }
        tasks[i].subtaskTotal = scoped.count
        tasks[i].subtaskDone = scoped.filter { $0.isDone }.count
    }

    func loadCollaborators() async {
        guard let pid = project?.id else { return }
        do {
            let list = try await service.listCollaborators(projectId: pid, forceRefresh: true)
            await MainActor.run {
                guard project?.id == pid else { return }
                collaborators = list
            }
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
            let list = try await service.listProjectElements(projectId: pid, forceRefresh: true)
            await MainActor.run {
                guard project?.id == pid else { return }
                elements = list
            }
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

    /// Save an element's git repo binding (path globs + optional branch pin).
    func updateElementRepoBinding(_ element: MWProjectElement, repoPaths: [String], repoBranch: String?) async {
        guard let pid = project?.id else { return }
        do {
            let updated = try await service.updateProjectElement(
                projectId: pid, elementId: element.id,
                repoPaths: repoPaths, repoBranch: repoBranch ?? ""
            )
            await MainActor.run {
                if let i = elements.firstIndex(where: { $0.id == element.id }) { elements[i] = updated }
            }
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    // MARK: - GitHub connection + commit scanning

    var isGitHubConnected: Bool { !(project?.githubRepo ?? "").isEmpty }
    var connectedGitHubRepo: String? { project?.githubRepo }
    var connectedGitHubBranch: String? { project?.githubBranch }

    /// Connect / change the project's GitHub repo (validated server-side).
    /// `repo` is owner/name; empty disconnects.
    func connectGitHubRepo(repo: String, branch: String?) async {
        guard let pid = project?.id else { return }
        do {
            let conn = try await service.setGitHubConnection(projectId: pid, repo: repo, branch: branch)
            await MainActor.run {
                project?.githubRepo = conn.repo
                project?.githubBranch = conn.branch
            }
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    func disconnectGitHubRepo() async {
        guard let pid = project?.id else { return }
        do {
            _ = try await service.setGitHubConnection(projectId: pid, repo: "", branch: nil)
            await MainActor.run {
                project?.githubRepo = nil
                project?.githubBranch = nil
                lastScanSummary = nil
                lastSyncSummary = nil
            }
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    /// Refresh pending suggestions from the server (e.g. on project open).
    func loadCommitSuggestions() async {
        guard let pid = project?.id else { return }
        do {
            let list = try await service.listCommitSuggestions(projectId: pid)
            await MainActor.run { regroupSuggestions(list) }
        } catch { /* non-fatal — suggestions are advisory */ }
    }

    /// Replace the keyed suggestion map from a flat list (server is source of truth).
    private func regroupSuggestions(_ list: [MWCommitSuggestion]) {
        commitSuggestions = Dictionary(grouping: list, by: { $0.taskId })
    }

    /// Pending suggestions for one subtask (used by the checklist chip).
    func suggestions(taskId: String, subtaskId: String) -> [MWCommitSuggestion] {
        (commitSuggestions[taskId] ?? []).filter { $0.subtaskId == subtaskId && $0.status == "pending" }
    }

    /// How many distinct subtasks on a task a commit may have completed (still
    /// pending accept) — drives the kanban card badge. Distinct on subtask_id so
    /// two commits hitting the same subtask count once.
    func pendingSuggestionCount(taskId: String) -> Int {
        let pending = (commitSuggestions[taskId] ?? []).filter { $0.status == "pending" }
        return Set(pending.map { $0.subtaskId }).count
    }

    func acceptSuggestion(_ s: MWCommitSuggestion) async {
        guard let pid = project?.id else { return }
        // Optimistic: drop the chip and tick the box locally.
        await MainActor.run {
            commitSuggestions[s.taskId]?.removeAll { $0.id == s.id }
            if var list = taskSubtasks[s.taskId], let i = list.firstIndex(where: { $0.id == s.subtaskId }) {
                list[i].isDone = true
                taskSubtasks[s.taskId] = list
                syncSubtaskCounts(taskId: s.taskId)
            }
        }
        do {
            try await service.acceptCommitSuggestion(projectId: pid, suggestionId: s.id)
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
            await loadSubtasks(taskId: s.taskId)
            await loadCommitSuggestions()
        }
    }

    func dismissSuggestion(_ s: MWCommitSuggestion) async {
        guard let pid = project?.id else { return }
        await MainActor.run { commitSuggestions[s.taskId]?.removeAll { $0.id == s.id } }
        do {
            try await service.dismissCommitSuggestion(projectId: pid, suggestionId: s.id)
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
            await loadCommitSuggestions()
        }
    }

    /// Pull element code from GitHub (server-side, read-only token) — no local
    /// clone or bookmark needed, works for any collaborator.
    func syncFromGitHub() async {
        guard let pid = project?.id else { return }
        if elements.isEmpty { await loadElements() }
        await MainActor.run { isSyncingRepo = true }
        do {
            let res = try await service.syncFromGitHub(projectId: pid)
            lastGitHubSyncAt[pid] = Date()
            await MainActor.run {
                isSyncingRepo = false
                lastSyncSummary = "GitHub: \(res.totalStored) files" + (res.repo.map { " · \($0)" } ?? "")
            }
        } catch {
            await MainActor.run { isSyncingRepo = false; errorMessage = error.localizedDescription }
        }
    }

    /// Auto-sync on Props-tab open, gated so it can't spam GitHub:
    ///  1. skip if a sync is already running (no concurrent calls)
    ///  2. skip if synced within the cooldown window (per project)
    ///  3. skip if no element has globs bound (nothing to fetch)
    /// Silent on failure (no error banner) — the manual button surfaces errors
    /// and bypasses the cooldown.
    func autoSyncFromGitHubIfStale() async {
        guard let pid = project?.id, !isSyncingRepo, isGitHubConnected else { return }
        if let last = lastGitHubSyncAt[pid], Date().timeIntervalSince(last) < githubSyncCooldown { return }
        if elements.isEmpty { await loadElements() }
        guard elements.contains(where: { !($0.repoPaths ?? []).isEmpty }) else { return }
        // Stamp BEFORE the await so a rapid second .task firing can't double-fire.
        lastGitHubSyncAt[pid] = Date()
        await MainActor.run { isSyncingRepo = true }
        do {
            let res = try await service.syncFromGitHub(projectId: pid)
            await MainActor.run { isSyncingRepo = false; lastSyncSummary = "GitHub: \(res.totalStored) files" }
        } catch {
            await MainActor.run { isSyncingRepo = false }  // silent on auto; keep the stamp so a failure doesn't retry-spam
        }
    }

    /// Manual "Scan commits": force a re-scan of recent commits (so a just-added
    /// ticket can match already-merged work). Chips appear on tickets.
    func scanCommitsFromGitHub() async {
        guard let pid = project?.id, !isScanningCommits else { return }
        await MainActor.run { isScanningCommits = true }
        do {
            let r = try await service.scanCommitsFromGitHub(projectId: pid, force: true)
            lastGitHubScanAt[pid] = Date()
            await MainActor.run {
                isScanningCommits = false
                regroupSuggestions(r.suggestions)
                lastScanSummary = "\(r.scanned) commit\(r.scanned == 1 ? "" : "s") · \(r.suggestions.count) suggestion\(r.suggestions.count == 1 ? "" : "s")"
            }
            // High-confidence matches auto-check subtasks server-side — refresh
            // task aggregates so card progress (X/Y) reflects them.
            if r.scanned > 0 { await loadTasks() }
        } catch {
            await MainActor.run { isScanningCommits = false; errorMessage = error.localizedDescription }
        }
    }

    /// Auto-scan the connected branch on Kanban open — gated so it "just happens"
    /// after you merge without spamming GitHub. Gates: not already scanning,
    /// 10-min per-project cooldown, repo connected. Silent on failure (the manual
    /// Scan button surfaces errors and bypasses the cooldown).
    func autoScanCommitsIfStale() async {
        guard let pid = project?.id, !isScanningCommits, isGitHubConnected else { return }
        if let last = lastGitHubScanAt[pid], Date().timeIntervalSince(last) < githubSyncCooldown { return }
        lastGitHubScanAt[pid] = Date()  // stamp before the await so a re-fire skips
        await MainActor.run { isScanningCommits = true }
        do {
            // Watermark scan: only NEW commits since the last scan (cheap).
            let r = try await service.scanCommitsFromGitHub(projectId: pid, force: false)
            await MainActor.run {
                isScanningCommits = false
                regroupSuggestions(r.suggestions)
                if !r.suggestions.isEmpty {
                    lastScanSummary = "\(r.scanned) commit\(r.scanned == 1 ? "" : "s") · \(r.suggestions.count) suggestion\(r.suggestions.count == 1 ? "" : "s")"
                }
            }
            // Reflect any server-side auto-checks (high-confidence matches).
            if r.scanned > 0 { await loadTasks() }
        } catch {
            await MainActor.run { isScanningCommits = false }  // silent on auto
        }
    }

    /// Register the GitHub push webhook so a merge auto-triggers a scan (no polling).
    func installGitHubWebhook() async {
        guard let pid = project?.id else { return }
        do {
            _ = try await service.installGitHubWebhook(projectId: pid)
            await MainActor.run { lastScanSummary = "Push auto-scan enabled" }
        } catch {
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
        // Spinner only on a cold load; a warm revalidate diff-updates in place.
        let wasEmpty = files.isEmpty && folders.isEmpty
        await MainActor.run { if wasEmpty { isLoadingFiles = true } }
        do {
            // Files + folders concurrently (was serial → doubled the latency).
            async let filesReq = service.listProjectFiles(projectId: pid, forceRefresh: true)
            async let foldersReq = service.listProjectFolders(projectId: pid, forceRefresh: true)
            let list = try await filesReq
            let fetchedFolders = try? await foldersReq
            await MainActor.run {
                guard project?.id == pid else { return }
                files = list
                if let fetchedFolders { folders = fetchedFolders }
                isLoadingFiles = false
                lastFilesFetch[pid] = Date()
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
        // Stamp up front so concurrent re-entries throttle even mid-sync.
        await MainActor.run { lastChatSyncFetch[pid] = Date() }
        if let added = try? await service.syncChatFiles(projectId: pid), added > 0 {
            await loadFiles()
        }
    }

    /// Links shared in the collab chat (URLs parsed from messages). Best-effort:
    /// failures leave the previous list intact rather than surfacing an error.
    func loadLinks() async {
        guard let pid = project?.id else { return }
        if let list = try? await service.listProjectLinks(projectId: pid, forceRefresh: true) {
            await MainActor.run {
                guard project?.id == pid else { return }
                links = list
                lastLinksFetch[pid] = Date()
            }
        }
    }

    /// Files-tab onAppear: never blank — paint from current state, revalidate
    /// only when empty or the last fetch is stale (>30s). Replaces the old
    /// unconditional per-entry refetch; the service cache + WS keep data fresh.
    func ensureFilesFresh() async {
        guard let pid = project?.id else { return }
        if files.isEmpty && folders.isEmpty { await loadFiles(); return }
        if !isFresh(lastFilesFetch, pid) { await loadFiles() }
    }

    /// Media-tab onAppear: files + (throttled) chat-file sync + links. Collapses
    /// the old always-3-network-calls-per-entry into throttled first-entry work.
    func ensureMediaFresh() async {
        guard let pid = project?.id else { return }
        await ensureFilesFresh()
        if !isFresh(lastChatSyncFetch, pid) { Task { await self.syncChatFiles() } }
        if !isFresh(lastLinksFetch, pid) { Task { await self.loadLinks() } }
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
        if let list = try? await service.listProjectFolders(projectId: pid, forceRefresh: true) {
            await MainActor.run {
                guard project?.id == pid else { return }
                folders = list
            }
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

