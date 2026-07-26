import Foundation
import AppKit

extension ProjectDetailViewModel {

    // MARK: - Collab: tasks

    /// Load the Done column beyond the current week (server-capped). Called when
    /// the user expands Done, or opens a board whose Done policy is cumulative.
    /// No-op once "all" is already loaded, so expanding twice costs one fetch.
    func loadAllDoneTasks() async {
        guard doneScope != "all", let pid = project?.id else { return }
        await MainActor.run { doneScope = "all" }
        // loadTasks() force-refreshes, so the week-scoped cache entry can't win.
        await loadTasks()
        // Older finishes may still be truncated by the server cap; the count
        // comes from the DB, not from what we managed to load.
        if let counts = try? await service.fetchDoneCount(projectId: pid) {
            await MainActor.run {
                guard project?.id == pid else { return }
                doneTotal = counts.total
            }
        }
    }

    func loadTasks() async {
        guard let pid = project?.id else { return }
        // Only show the spinner on a cold load; a warm revalidate diff-updates
        // in place so there's no flicker. forceRefresh: this IS the revalidate
        // half of SWR (the cache was already painted by loadProject).
        let wasEmpty = tasks.isEmpty
        await MainActor.run { if wasEmpty { isLoadingTasks = true } }
        do {
            let list = try await service.listProjectTasks(projectId: pid, forceRefresh: true,
                                                          doneScope: doneScope)
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
                logActivity("plus.circle", isDeal ? "added deal \u{201C}\(title)\u{201D}" : "added task \u{201C}\(title)\u{201D}")
            }
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    /// Duplicate an existing task: same title (with a "(copy)" suffix so the
    /// two are distinguishable), column, priority, assignee, description,
    /// category, element, and checklist item titles (created fresh/not-done —
    /// completion state isn't carried over, matching how `createProjectTask`'s
    /// `subtasks` param already works for a brand-new task). Attachments are
    /// NOT duplicated — no existing S3-file-copy precedent in the codebase,
    /// and re-pointing/re-uploading them is a separate concern.
    func duplicateTask(_ task: MWProjectTask) async {
        guard let pid = project?.id else { return }
        let subtaskTitles: [String]
        if let cached = taskSubtasks[task.id] {
            subtaskTitles = cached.map { $0.title }
        } else {
            subtaskTitles = (try? await service.listSubtasks(projectId: pid, taskId: task.id))?.map { $0.title } ?? []
        }
        await addTask(
            title: "\(task.title) (copy)",
            column: task.boardColumn,
            pipelineColumn: task.pipelineColumn ?? "lead",
            priority: task.priority,
            assignedTo: task.assignedTo,
            description: task.description,
            category: task.category,
            elementId: task.elementId,
            subtasks: subtaskTitles.isEmpty ? nil : subtaskTitles
        )
    }

    // MARK: - Collab: realtime task fan-out (project WS task.created/updated/deleted)

    /// Register this VM's task-event handlers in the project WS per-owner
    /// registry (keyed by projectId — see ProjectWebSocket.TaskEventHandlers
    /// for why it's a registry, not single closures). Call once per
    /// loadProject; re-calling just replaces this VM's entry. `currentUserId`
    /// (from AppState) is captured so self-echoes from our own create /
    /// update / delete don't double-apply. `showToasts: false` for embedded /
    /// aux instances so a project open in two panes doesn't double-toast.
    @MainActor
    func attachTaskRealtime(currentUserId: String?, projectId: String, showToasts: Bool = true) {
        print("[ProjectVM] attachTaskRealtime user=\(currentUserId ?? "nil") project=\(projectId) toasts=\(showToasts)")
        self.currentUserId = currentUserId
        let handlers = ProjectWebSocket.TaskEventHandlers(
            onCreated: { [weak self] dict in
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
                        if showToasts {
                            self.pushTaskToast(actorId: actorId, action: "added", title: task.title,
                                               systemImage: "plus.rectangle.on.rectangle")
                        }
                    }
                } else {
                    // Payload didn't decode (schema drift / partial row) —
                    // fall back to a full list refetch so the board still
                    // converges instead of silently dropping the event.
                    Task { await self.loadTasks() }
                }
            },
            onUpdated: { [weak self] dict in
                print("[ProjectVM] onTaskUpdated task=\(dict["id"] ?? "?") actor=\(dict["actor_id"] ?? "?") column=\(dict["board_column"] ?? "?")")
                guard let self else { return }
                let actorId = dict["actor_id"] as? String
                if let task = Self.decodeTask(dict) {
                    Task { @MainActor in
                        // Capture the prior column before applying so we can tell a
                        // lane move from an in-place edit for the toast copy.
                        let prevColumn = self.tasks.first(where: { $0.id == task.id })?.boardColumn
                        self.applyTaskUpdated(task)
                        if showToasts, actorId != self.currentUserId {
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
                } else {
                    Task { await self.loadTasks() }
                }
            },
            onDeleted: { [weak self] taskId, actorId in
                print("[ProjectVM] onTaskDeleted task=\(taskId) actor=\(actorId ?? "?")")
                guard let self else { return }
                if let actorId, actorId == self.currentUserId { return }
                Task { @MainActor in
                    let title = self.tasks.first(where: { $0.id == taskId })?.title
                    self.applyTaskDeleted(taskId)
                    if showToasts {
                        self.pushTaskToast(actorId: actorId, action: "removed", title: title,
                                           systemImage: "trash")
                    }
                }
            },
        )
        ProjectWebSocket.shared.registerTaskHandlers(owner: self, projectId: projectId, handlers: handlers)
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
    func replacePreservingAggregates(_ updated: MWProjectTask) {
        guard let i = tasks.firstIndex(where: { $0.id == updated.id }) else { return }
        var merged = updated
        if merged.reviewCycleCount == nil { merged.reviewCycleCount = tasks[i].reviewCycleCount }
        if merged.subtaskTotal == nil { merged.subtaskTotal = tasks[i].subtaskTotal }
        if merged.subtaskDone == nil { merged.subtaskDone = tasks[i].subtaskDone }
        if merged.updateCount == nil { merged.updateCount = tasks[i].updateCount }
        if merged.recentEventIds == nil { merged.recentEventIds = tasks[i].recentEventIds }
        if merged.assignedAvatarUrl == nil { merged.assignedAvatarUrl = tasks[i].assignedAvatarUrl }
        if merged.createdBy == nil { merged.createdBy = tasks[i].createdBy }
        if merged.createdByName == nil { merged.createdByName = tasks[i].createdByName }
        if merged.createdByAvatarUrl == nil { merged.createdByAvatarUrl = tasks[i].createdByAvatarUrl }
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

    /// Reviewer denies a completed checklist item with a reason: reopen it +
    /// log a `subtask_rejected` audit event. Optimistic uncheck.
    func denySubtask(taskId: String, subtaskId: String, reason: String, severity: String?) async {
        guard let pid = project?.id else { return }
        await MainActor.run {
            if var list = taskSubtasks[taskId],
               let i = list.firstIndex(where: { $0.id == subtaskId }) {
                list[i].isDone = false
                taskSubtasks[taskId] = list
                syncSubtaskCounts(taskId: taskId)
            }
            // The denial overturns the commit→completion server-side; drop it now.
            commitCompletions[subtaskId] = nil
        }
        do {
            let updated = try await service.denySubtask(
                projectId: pid, taskId: taskId, subtaskId: subtaskId, reason: reason, severity: severity
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
                if var list = taskSubtasks[taskId],
                   let i = list.firstIndex(where: { $0.id == subtaskId }) {
                    list[i].isDone = true
                    taskSubtasks[taskId] = list
                    syncSubtaskCounts(taskId: taskId)
                }
                errorMessage = error.localizedDescription
            }
        }
    }

    /// Reviewer approves a task out of review → done with an optional sign-off
    /// note. Replaces the task (preserving aggregates) so the board reflects done.
    /// Returns true on success so the sheet only closes when the move landed.
    func approveTask(taskId: String, note: String?) async -> Bool {
        guard let pid = project?.id else { return false }
        do {
            let updated = try await service.approveTask(projectId: pid, taskId: taskId, note: note)
            await MainActor.run { replacePreservingAggregates(updated) }
            return true
        } catch {
            await loadTasks()
            await MainActor.run { errorMessage = error.localizedDescription }
            return false
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
    func syncSubtaskCounts(taskId: String) {
        guard let list = taskSubtasks[taskId],
              let i = tasks.firstIndex(where: { $0.id == taskId }) else { return }
        // Scope to the current round (max round_index) so the card face matches
        // the live checklist — past-round items are archived, not counted.
        let current = list.map { $0.roundIndex ?? 1 }.max() ?? 1
        let scoped = list.filter { ($0.roundIndex ?? 1) == current }
        tasks[i].subtaskTotal = scoped.count
        tasks[i].subtaskDone = scoped.filter { $0.isDone }.count
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
                logActivity("checkmark.circle.fill", "completed \u{201C}\(title)\u{201D}")
            } else {
                logActivity("arrow.uturn.left", "reopened \u{201C}\(title)\u{201D}")
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
                logActivity("arrow.uturn.backward", "sent \u{201C}\(updated.title)\u{201D} back for changes")
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
}
