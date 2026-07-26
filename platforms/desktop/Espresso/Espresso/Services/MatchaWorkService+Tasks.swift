import Foundation

extension MatchaWorkService {
    // MARK: - Tasks

    func cachedProjectTasks(_ projectId: String) -> [MWProjectTask]? { cachedValue(projectTasksCache[projectId]) }
    func invalidateProjectTasks(projectId: String) { projectTasksCache.removeValue(forKey: projectId) }

    /// `doneScope: "week"` (the server default) returns only this week's Done
    /// cards; `"all"` returns the most recently finished, server-capped. Every
    /// other column comes back whole either way. The board opens on "week" and
    /// re-requests "all" when the user expands the Done column.
    func listProjectTasks(projectId: String, forceRefresh: Bool = false,
                          doneScope: String = "week") async throws -> [MWProjectTask] {
        if !forceRefresh, let cached = cachedValue(projectTasksCache[projectId]) { return cached }
        let result: [MWProjectTask] = try await client.request(
            method: "GET", path: "\(basePath)/projects/\(projectId)/tasks?done_scope=\(doneScope)")
        projectTasksCache[projectId] = MWCacheEntry(value: result, expiresAt: Date().addingTimeInterval(cacheTTL))
        return result
    }

    /// `{total, this_week}` for the Done column — the full counts the task list
    /// withholds. Used to label the board's "show N finished earlier" expander
    /// on paths that don't go through the project bundle.
    func fetchDoneCount(projectId: String) async throws -> MWDoneCount {
        try await client.request(method: "GET", path: "\(basePath)/projects/\(projectId)/tasks/done-count")
    }

    func createProjectTask(
        projectId: String,
        title: String,
        boardColumn: String = "todo",
        pipelineColumn: String = "lead",
        description: String? = nil,
        priority: String = "medium",
        dueDate: String? = nil,
        assignedTo: String? = nil,
        category: String? = nil,
        elementId: String? = nil,
        dealValue: Double? = nil,
        probability: Int? = nil,
        contactName: String? = nil,
        contactCompany: String? = nil,
        contactEmail: String? = nil,
        contactPhone: String? = nil,
        outcome: String? = nil,
        lossReason: String? = nil,
        nextActionAt: String? = nil,
        expectedClose: String? = nil,
        subtasks: [String]? = nil
    ) async throws -> MWProjectTask {
        struct Body: Encodable {
            let title: String
            let description: String?
            let board_column: String
            let pipeline_column: String
            let priority: String
            let due_date: String?
            let assigned_to: String?
            let category: String?
            let element_id: String?
            let deal_value: Double?
            let probability: Int?
            let contact_name: String?
            let contact_company: String?
            let contact_email: String?
            let contact_phone: String?
            let outcome: String?
            let loss_reason: String?
            let next_action_at: String?
            let expected_close: String?
            // Optional checklist created alongside the task (AI-drafted tickets).
            let subtasks: [String]?
        }
        defer { invalidateProjectTasks(projectId: projectId) }
        return try await client.request(
            method: "POST",
            path: "\(basePath)/projects/\(projectId)/tasks",
            body: Body(
                title: title, description: description,
                board_column: boardColumn, pipeline_column: pipelineColumn,
                priority: priority, due_date: dueDate, assigned_to: assignedTo,
                category: category, element_id: elementId,
                deal_value: dealValue, probability: probability,
                contact_name: contactName, contact_company: contactCompany,
                contact_email: contactEmail, contact_phone: contactPhone,
                outcome: outcome, loss_reason: lossReason,
                next_action_at: nextActionAt, expected_close: expectedClose,
                subtasks: subtasks
            )
        )
    }

    struct ProjectTaskPatch: Encodable {
        var title: String?
        var description: String?
        var boardColumn: String?
        var pipelineColumn: String?
        var priority: String?
        var status: String?
        var dueDate: String?
        var assignedTo: String?
        var progressNote: String?
        var elementId: String?
        // Sales-pipeline fields. Same encodeIfPresent contract: nil = leave
        // unchanged; an empty string clears a text/date field server-side.
        var dealValue: Double?
        var probability: Int?
        var contactName: String?
        var contactCompany: String?
        var contactEmail: String?
        var contactPhone: String?
        var outcome: String?
        var lossReason: String?
        var nextActionAt: String?
        var expectedClose: String?

        enum CodingKeys: String, CodingKey {
            case title, description, priority, status, outcome, probability
            case boardColumn = "board_column"
            case pipelineColumn = "pipeline_column"
            case dueDate = "due_date"
            case assignedTo = "assigned_to"
            case progressNote = "progress_note"
            case elementId = "element_id"
            case dealValue = "deal_value"
            case contactName = "contact_name"
            case contactCompany = "contact_company"
            case contactEmail = "contact_email"
            case contactPhone = "contact_phone"
            case lossReason = "loss_reason"
            case nextActionAt = "next_action_at"
            case expectedClose = "expected_close"
        }

        /// Custom encode — emit only the fields that were actually set.
        /// Default Codable serializes nil as JSON `null`, and the server
        /// route treats any present key (including nulls) as a patch
        /// instruction; that meant a single-field toggle (e.g.
        /// `{status: "completed"}`) was being sent as
        /// `{title: null, board_column: null, status: "completed", ...}`,
        /// the route then ran every branch, and the board_column
        /// validator rejected `None` with a 400 — the kanban toggle
        /// silently failed and the optimistic UI snapped back on
        /// reload.
        func encode(to encoder: Encoder) throws {
            var c = encoder.container(keyedBy: CodingKeys.self)
            try c.encodeIfPresent(title, forKey: .title)
            try c.encodeIfPresent(description, forKey: .description)
            try c.encodeIfPresent(boardColumn, forKey: .boardColumn)
            try c.encodeIfPresent(pipelineColumn, forKey: .pipelineColumn)
            try c.encodeIfPresent(priority, forKey: .priority)
            try c.encodeIfPresent(status, forKey: .status)
            try c.encodeIfPresent(dueDate, forKey: .dueDate)
            try c.encodeIfPresent(assignedTo, forKey: .assignedTo)
            try c.encodeIfPresent(progressNote, forKey: .progressNote)
            try c.encodeIfPresent(elementId, forKey: .elementId)
            // Sales-pipeline fields — same encodeIfPresent contract (nil = omit,
            // so the board-toggle 400-guard above still holds). Without these
            // the TaskEditorSheet's deal edits were silently dropped on the wire.
            try c.encodeIfPresent(dealValue, forKey: .dealValue)
            try c.encodeIfPresent(probability, forKey: .probability)
            try c.encodeIfPresent(contactName, forKey: .contactName)
            try c.encodeIfPresent(contactCompany, forKey: .contactCompany)
            try c.encodeIfPresent(contactEmail, forKey: .contactEmail)
            try c.encodeIfPresent(contactPhone, forKey: .contactPhone)
            try c.encodeIfPresent(outcome, forKey: .outcome)
            try c.encodeIfPresent(lossReason, forKey: .lossReason)
            try c.encodeIfPresent(nextActionAt, forKey: .nextActionAt)
            try c.encodeIfPresent(expectedClose, forKey: .expectedClose)
        }
    }

    func updateProjectTask(
        projectId: String,
        taskId: String,
        patch: ProjectTaskPatch
    ) async throws -> MWProjectTask {
        defer { invalidateProjectTasks(projectId: projectId) }
        return try await client.request(
            method: "PATCH",
            path: "\(basePath)/projects/\(projectId)/tasks/\(taskId)",
            body: patch
        )
    }

    /// Open a new round on a kanban ticket. Creates the "suggested fix"
    /// subtask + logs a `round_started` event + (optionally) a kick-off note
    /// with attachments. Rounds chain together as modular sub-todos inside
    /// one ticket; the new round inherits context from the previous round's
    /// completed work via the client-side "Fixed in Round N-1" summary.
    func startNewRound(
        projectId: String,
        taskId: String,
        suggestedFixTitle: String,
        body: String?,
        attachmentIds: [String]? = nil
    ) async throws {
        struct Req: Encodable {
            let suggested_fix_title: String
            let body: String?
            let attachment_ids: [String]?
        }
        struct Res: Decodable { let ok: Bool? }
        let _: Res = try await client.request(
            method: "POST",
            path: "\(basePath)/projects/\(projectId)/tasks/\(taskId)/rounds",
            body: Req(
                suggested_fix_title: suggestedFixTitle,
                body: body,
                attachment_ids: (attachmentIds?.isEmpty ?? true) ? nil : attachmentIds
            )
        )
    }

    /// Log a sales follow-up activity (call/email/note/meeting) onto a task's
    /// history timeline. Renders in the existing task-viewer timeline.
    /// `attachmentIds` (optional) links the note to existing mw_project_files
    /// rows for the task — upload via `uploadTaskFile` first, then pass the
    /// returned ids here so the note renders inline thumbnails.
    func logTaskActivity(projectId: String, taskId: String, kind: String, body: String?, attachmentIds: [String]? = nil, replyTo: String? = nil) async throws {
        struct Req: Encodable {
            let kind: String
            let body: String?
            let attachment_ids: [String]?
            let reply_to: String?
        }
        struct Res: Decodable { let ok: Bool? }
        let _: Res = try await client.request(
            method: "POST",
            path: "\(basePath)/projects/\(projectId)/tasks/\(taskId)/activity",
            body: Req(kind: kind, body: body, attachment_ids: (attachmentIds?.isEmpty ?? true) ? nil : attachmentIds, reply_to: replyTo)
        )
    }

    /// Reviewer sends a task back for changes: server bounces review →
    /// changes_requested, stores the note, and emails the assignee. Returns the
    /// updated task.
    func rejectTask(projectId: String, taskId: String, note: String) async throws -> MWProjectTask {
        struct Req: Encodable { let note: String }
        defer { invalidateProjectTasks(projectId: projectId) }
        return try await client.request(
            method: "POST",
            path: "\(basePath)/projects/\(projectId)/tasks/\(taskId)/reject",
            body: Req(note: note)
        )
    }

    /// Reviewer approves a task out of review → done, recording a `review_approved`
    /// sign-off (approver + timestamp + optional note). Returns the updated task.
    func approveTask(projectId: String, taskId: String, note: String?) async throws -> MWProjectTask {
        struct Req: Encodable { let note: String? }
        defer { invalidateProjectTasks(projectId: projectId) }
        return try await client.request(
            method: "POST",
            path: "\(basePath)/projects/\(projectId)/tasks/\(taskId)/approve",
            body: Req(note: (note?.isEmpty ?? true) ? nil : note)
        )
    }

    /// Natural-language → structured ticket draft via Gemini (no DB write).
    /// `model` is the header selector's value (same plumbing as threads).
    func draftTaskFromPrompt(projectId: String, prompt: String, model: String? = nil) async throws -> MWTaskDraft {
        struct Req: Encodable { let prompt: String; let model: String? }
        return try await client.request(
            method: "POST",
            path: "\(basePath)/projects/\(projectId)/tasks/ai-draft",
            body: Req(prompt: prompt, model: model)
        )
    }

    func deleteProjectTask(projectId: String, taskId: String) async throws {
        _ = try await client.requestData(
            method: "DELETE",
            path: "\(basePath)/projects/\(projectId)/tasks/\(taskId)"
        )
        invalidateProjectTasks(projectId: projectId)
    }

    // MARK: - Dashboard

    /// Pending tasks across all projects in the current user's company.
    func listOpenTasks() async throws -> [MWOpenTask] {
        try await client.request(method: "GET", path: "\(basePath)/tasks/open")
    }

    /// Recent activity feed (projects, tasks, threads) within the last 14 days.
    func listRecentActivity() async throws -> [MWActivityItem] {
        try await client.request(method: "GET", path: "\(basePath)/activity/recent")
    }

    func markProjectComplete(projectId: String) async throws {
        _ = try await client.requestData(
            method: "POST",
            path: "\(basePath)/projects/\(projectId)/complete"
        )
    }

    /// 1-click Gemini Flash Lite catch-up summary of a ticket — where the work
    /// stands + what's been done. Ephemeral; the server doesn't persist it.
    func summarizeTask(projectId: String, taskId: String) async throws -> String {
        struct SummaryResponse: Decodable { let summary: String }
        let resp: SummaryResponse = try await client.request(
            method: "POST",
            path: "\(basePath)/projects/\(projectId)/tasks/\(taskId)/summarize"
        )
        return resp.summary
    }

    /// Accepted commit→subtask completions for a task (one latest per subtask):
    /// which commit completed each done item, for the in-review audit UI.
    func listCommitCompletions(projectId: String, taskId: String) async throws -> [MWCommitSuggestion] {
        try await client.request(
            method: "GET",
            path: "\(basePath)/projects/\(projectId)/tasks/\(taskId)/commit-completions"
        )
    }

    // MARK: - Task history + activity feed

    /// Audit-trail timeline for a single kanban task. Newest-last (server
    /// returns ASC) so the timeline reads top-to-bottom chronologically.
    func fetchTaskHistory(projectId: String, taskId: String) async throws -> [MWTaskHistoryEntry] {
        try await client.request(
            method: "GET",
            path: "\(basePath)/projects/\(projectId)/tasks/\(taskId)/history"
        )
    }

    /// Project-scoped activity feed for the Overview tab. Mixed sources
    /// (task history, file uploads, collaborator joins). Newest-first.
    func fetchProjectActivity(projectId: String, limit: Int = 50) async throws -> [MWProjectActivityEntry] {
        try await client.request(
            method: "GET",
            path: "\(basePath)/projects/\(projectId)/activity?limit=\(limit)"
        )
    }

    /// Weekly Work Replay: board-column snapshot as of `weekStart` (Monday
    /// 00:00 Pacific) plus every history event through the following Sunday
    /// 11:59:59pm, ascending. `weekStart` must be ISO8601 UTC.
    func fetchWeeklyReplay(projectId: String, weekStart: String) async throws -> MWWeeklyReplay {
        guard let encoded = weekStart.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) else {
            throw URLError(.badURL)
        }
        return try await client.request(
            method: "GET",
            path: "\(basePath)/projects/\(projectId)/history/replay?week_start=\(encoded)"
        )
    }

    // MARK: - Task file attachments

    func listTaskFiles(projectId: String, taskId: String) async throws -> [MWProjectFile] {
        try await client.request(
            method: "GET",
            path: "\(basePath)/projects/\(projectId)/tasks/\(taskId)/files"
        )
    }

    func uploadTaskFile(
        projectId: String,
        taskId: String,
        file: (data: Data, filename: String, mimeType: String)
    ) async throws -> MWProjectFile {
        // Task attachments are embedded in the kanban task list rows.
        defer { invalidateProjectTasks(projectId: projectId) }
        var multipart = MultipartUploadBuilder()
        multipart.addFile(name: "file", filename: file.filename, mimeType: file.mimeType, data: file.data)
        let (body, contentType) = multipart.finalize()

        guard let url = URL(string: "\(client.baseURL)\(basePath)/projects/\(projectId)/tasks/\(taskId)/files") else {
            throw APIError.invalidURL
        }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue(contentType, forHTTPHeaderField: "Content-Type")
        if let token = client.accessToken {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        request.httpBody = body

        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
            let msg = String(data: data, encoding: .utf8) ?? "Upload failed"
            throw APIError.httpError((response as? HTTPURLResponse)?.statusCode ?? 0, msg)
        }
        return try JSONDecoder().decode(MWProjectFile.self, from: data)
    }

    func deleteTaskFile(projectId: String, taskId: String, fileId: String) async throws {
        _ = try await client.requestData(
            method: "DELETE",
            path: "\(basePath)/projects/\(projectId)/tasks/\(taskId)/files/\(fileId)"
        )
        invalidateProjectTasks(projectId: projectId)
    }

    // MARK: - Task subtasks (checklist)

    func listSubtasks(projectId: String, taskId: String) async throws -> [MWSubtask] {
        try await client.request(
            method: "GET",
            path: "\(basePath)/projects/\(projectId)/tasks/\(taskId)/subtasks"
        )
    }

    func createSubtask(projectId: String, taskId: String, title: String) async throws -> MWSubtask {
        struct Req: Encodable { let title: String }
        // Subtask counts are aggregated onto the kanban task list rows.
        defer { invalidateProjectTasks(projectId: projectId) }
        return try await client.request(
            method: "POST",
            path: "\(basePath)/projects/\(projectId)/tasks/\(taskId)/subtasks",
            body: Req(title: title)
        )
    }

    /// Toggle one checklist item. Sends only `is_done` so we never accidentally
    /// blank the title/position (the backend treats any present key as an edit).
    func setSubtaskDone(projectId: String, taskId: String, subtaskId: String, isDone: Bool) async throws -> MWSubtask {
        struct Req: Encodable { let is_done: Bool }
        defer { invalidateProjectTasks(projectId: projectId) }
        return try await client.request(
            method: "PATCH",
            path: "\(basePath)/projects/\(projectId)/tasks/\(taskId)/subtasks/\(subtaskId)",
            body: Req(is_done: isDone)
        )
    }

    func deleteSubtask(projectId: String, taskId: String, subtaskId: String) async throws {
        _ = try await client.requestData(
            method: "DELETE",
            path: "\(basePath)/projects/\(projectId)/tasks/\(taskId)/subtasks/\(subtaskId)"
        )
        invalidateProjectTasks(projectId: projectId)
    }

    /// Reviewer denies a completed checklist item: reopen it (is_done=false) with
    /// a reason → server logs a `subtask_rejected` audit event and rolls the item
    /// into the next round on send-back.
    func denySubtask(projectId: String, taskId: String, subtaskId: String, reason: String, severity: String?) async throws -> MWSubtask {
        struct Req: Encodable { let is_done: Bool; let reason: String; let severity: String? }
        defer { invalidateProjectTasks(projectId: projectId) }
        return try await client.request(
            method: "PATCH",
            path: "\(basePath)/projects/\(projectId)/tasks/\(taskId)/subtasks/\(subtaskId)",
            body: Req(is_done: false, reason: reason, severity: severity)
        )
    }

    /// Assign (or unassign) a subtask. Send `assigned_to` only so the title /
    /// done state aren't touched. `nil` → empty string → server clears it.
    func setSubtaskAssignee(projectId: String, taskId: String, subtaskId: String, assignedTo: String?) async throws -> MWSubtask {
        struct Req: Encodable { let assigned_to: String }
        defer { invalidateProjectTasks(projectId: projectId) }
        return try await client.request(
            method: "PATCH",
            path: "\(basePath)/projects/\(projectId)/tasks/\(taskId)/subtasks/\(subtaskId)",
            body: Req(assigned_to: assignedTo ?? "")
        )
    }

    // MARK: - Note (section) comments

    func listSectionComments(projectId: String, sectionId: String) async throws -> [MWSectionComment] {
        try await client.request(
            method: "GET",
            path: "\(basePath)/projects/\(projectId)/sections/\(sectionId)/comments"
        )
    }

    func addSectionComment(
        projectId: String,
        sectionId: String,
        content: String,
        replyToCommentId: String? = nil,
        anchorStart: Int? = nil,
        anchorEnd: Int? = nil,
        quotedText: String? = nil
    ) async throws -> MWSectionComment {
        struct Body: Encodable {
            let content: String
            let reply_to_comment_id: String?
            let anchor_start: Int?
            let anchor_end: Int?
            let quoted_text: String?
        }
        return try await client.request(
            method: "POST",
            path: "\(basePath)/projects/\(projectId)/sections/\(sectionId)/comments",
            body: Body(
                content: content,
                reply_to_comment_id: replyToCommentId,
                anchor_start: anchorStart,
                anchor_end: anchorEnd,
                quoted_text: quotedText
            )
        )
    }

    func resolveSectionComment(projectId: String, sectionId: String, commentId: String, resolved: Bool) async throws -> MWSectionComment {
        struct Body: Encodable { let resolved: Bool }
        return try await client.request(
            method: "PATCH",
            path: "\(basePath)/projects/\(projectId)/sections/\(sectionId)/comments/\(commentId)/resolve",
            body: Body(resolved: resolved)
        )
    }

    func deleteSectionComment(projectId: String, sectionId: String, commentId: String) async throws {
        _ = try await client.requestData(
            method: "DELETE",
            path: "\(basePath)/projects/\(projectId)/sections/\(sectionId)/comments/\(commentId)"
        )
    }

    struct BlogSubmitResult: Codable {
        let id: String
        let slug: String
        let resubmitted: Bool
    }

    func submitBlogForReview(projectId: String, notes: String? = nil) async throws -> BlogSubmitResult {
        struct Body: Codable { let notes: String? }
        return try await client.request(
            method: "POST",
            path: "\(basePath)/projects/\(projectId)/submit-blog",
            body: Body(notes: notes)
        )
    }

    struct BlogMediaUpload: Codable {
        let url: String
        let kind: String
        let filename: String?
        let size: Int?
    }

    func uploadBlogMedia(
        projectId: String,
        file: (data: Data, filename: String, mimeType: String)
    ) async throws -> BlogMediaUpload {
        var multipart = MultipartUploadBuilder()
        multipart.addFile(name: "file", filename: file.filename, mimeType: file.mimeType, data: file.data)
        let (body, contentType) = multipart.finalize()

        guard let url = URL(string: "\(client.baseURL)\(basePath)/projects/\(projectId)/blog-media") else {
            throw APIError.invalidURL
        }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue(contentType, forHTTPHeaderField: "Content-Type")
        if let token = client.accessToken {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        request.httpBody = body

        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
            let msg = String(data: data, encoding: .utf8) ?? "Upload failed"
            throw APIError.httpError((response as? HTTPURLResponse)?.statusCode ?? 0, msg)
        }
        return try JSONDecoder().decode(BlogMediaUpload.self, from: data)
    }
}
