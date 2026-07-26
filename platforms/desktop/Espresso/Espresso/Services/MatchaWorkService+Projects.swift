import Foundation

extension MatchaWorkService {
    // MARK: - Projects

    func listProjects(status: String? = nil, forceRefresh: Bool = false) async throws -> [MWProject] {
        let key = status ?? "__all__"
        if !forceRefresh, let cached = cachedValue(projectListCache[key]) {
            return cached
        }
        var path = "\(basePath)/projects"
        if let s = status { path += "?status=\(s)" }
        let result: [MWProject] = try await client.request(method: "GET", path: path)
        projectListCache[key] = MWCacheEntry(
            value: result,
            expiresAt: Date().addingTimeInterval(cacheTTL)
        )
        return result
    }

    func createProject(title: String, projectType: String = "general", icon: String? = nil) async throws -> MWProject {
        struct Body: Codable { let title: String; let projectType: String; let icon: String?
            enum CodingKeys: String, CodingKey { case title; case projectType = "project_type"; case icon }
        }
        let project: MWProject = try await client.request(method: "POST", path: "\(basePath)/projects", body: Body(title: title, projectType: projectType, icon: icon))
        invalidateProjectLists()
        return project
    }

    /// Last cached project detail (if still fresh) — used to paint instantly on
    /// project switch while a fresh copy revalidates in the background.
    func cachedProjectDetail(_ id: String) -> MWProject? { cachedValue(projectDetailCache[id]) }

    func invalidateProjectDetail(id: String) { projectDetailCache.removeValue(forKey: id) }

    func getProjectDetail(id: String, forceRefresh: Bool = false) async throws -> MWProject {
        if !forceRefresh, let cached = cachedValue(projectDetailCache[id]) { return cached }
        let proj: MWProject = try await client.request(method: "GET", path: "\(basePath)/projects/\(id)")
        projectDetailCache[id] = MWCacheEntry(value: proj, expiresAt: Date().addingTimeInterval(cacheTTL))
        return proj
    }

    /// One-shot project open: detail + tasks (with attachments) + files +
    /// folders + links + collaborators + elements in a single round-trip.
    /// Warms every per-project cache so the detail view + each tab paint from
    /// cache without firing the six individual GETs. Used on the cold path of
    /// ProjectDetailViewModel.loadProject.
    func getProjectBundle(id: String) async throws -> MWProjectBundle {
        let bundle: MWProjectBundle = try await client.request(method: "GET", path: "\(basePath)/projects/\(id)/bundle")
        let exp = Date().addingTimeInterval(cacheTTL)
        projectDetailCache[id] = MWCacheEntry(value: bundle.project, expiresAt: exp)
        projectTasksCache[id] = MWCacheEntry(value: bundle.tasks, expiresAt: exp)
        projectFilesCache[id] = MWCacheEntry(value: bundle.files, expiresAt: exp)
        projectFoldersCache[id] = MWCacheEntry(value: bundle.folders, expiresAt: exp)
        projectLinksCache[id] = MWCacheEntry(value: bundle.links, expiresAt: exp)
        projectCollaboratorsCache[id] = MWCacheEntry(value: bundle.collaborators, expiresAt: exp)
        projectElementsCache[id] = MWCacheEntry(value: bundle.elements, expiresAt: exp)
        return bundle
    }

    @discardableResult
    func setProjectPinned(id: String, pinned: Bool) async throws -> Bool {
        struct Body: Codable { let is_pinned: Bool }
        struct Res: Codable { let is_pinned: Bool }
        let res: Res = try await client.request(
            method: "POST",
            path: "\(basePath)/projects/\(id)/pin",
            body: Body(is_pinned: pinned),
        )
        invalidateProjectLists()
        return res.is_pinned
    }

    @discardableResult
    func updateProjectMeta(id: String, title: String? = nil, isPinned: Bool? = nil, status: String? = nil, icon: String? = nil) async throws -> MWProject {
        defer { invalidateProjectLists(); invalidateProjectDetail(id: id) }
        struct Body: Codable { let title: String?; let isPinned: Bool?; let status: String?; let icon: String?
            enum CodingKeys: String, CodingKey { case title; case isPinned = "is_pinned"; case status; case icon }
        }
        return try await client.request(method: "PATCH", path: "\(basePath)/projects/\(id)", body: Body(title: title, isPinned: isPinned, status: status, icon: icon))
    }

    /// Toggle sales-pipeline mode for a project. Persisted to
    /// project_data.pipeline_mode (merged server-side). Returns the updated
    /// project so the caller can refresh `pipelineMode`.
    func setPipelineMode(projectId: String, enabled: Bool) async throws -> MWProject {
        struct Body: Codable { let enabled: Bool }
        return try await client.request(
            method: "PATCH",
            path: "\(basePath)/projects/\(projectId)/pipeline-mode",
            body: Body(enabled: enabled)
        )
    }

    func archiveProject(id: String) async throws {
        _ = try await client.requestData(method: "DELETE", path: "\(basePath)/projects/\(id)")
        invalidateProjectLists()
        await WorkDetailVMStore.shared.evictProject(id)
    }

    func deleteProject(id: String) async throws {
        _ = try await client.requestData(method: "DELETE", path: "\(basePath)/projects/\(id)/permanent")
        invalidateProjectLists()
        await WorkDetailVMStore.shared.evictProject(id)
    }

    func unarchiveProject(id: String) async throws {
        _ = try await client.requestData(method: "POST", path: "\(basePath)/projects/\(id)/unarchive")
        invalidateProjectLists()
    }

    func addProjectSection(projectId: String, title: String, content: String = "") async throws -> MWProject {
        struct Body: Codable { let title: String; let content: String }
        return try await client.request(method: "POST", path: "\(basePath)/projects/\(projectId)/sections", body: Body(title: title, content: content))
    }

    func updateProjectSection(projectId: String, sectionId: String, title: String? = nil, content: String? = nil) async throws -> MWProject {
        struct Body: Codable { let title: String?; let content: String? }
        return try await client.request(method: "PUT", path: "\(basePath)/projects/\(projectId)/sections/\(sectionId)", body: Body(title: title, content: content))
    }

    func deleteProjectSection(projectId: String, sectionId: String) async throws -> MWProject {
        try await client.request(method: "DELETE", path: "\(basePath)/projects/\(projectId)/sections/\(sectionId)")
    }

    /// Result of emailing a note: which recipients the server accepted vs. failed.
    struct EmailNoteResult: Codable {
        let ok: Bool
        let sent: [String]
        let failed: [String]
    }

    /// Email a single note as a PDF attachment to one or more recipients
    /// (collaborator emails + free-text). Sends immediately server-side.
    func emailProjectSection(projectId: String, sectionId: String, recipients: [String], subject: String?, message: String?) async throws -> EmailNoteResult {
        struct Body: Codable { let recipients: [String]; let subject: String?; let message: String? }
        return try await client.request(
            method: "POST",
            path: "\(basePath)/projects/\(projectId)/sections/\(sectionId)/email",
            body: Body(recipients: recipients, subject: subject, message: message)
        )
    }

    func reorderProjectSections(projectId: String, sectionIds: [String]) async throws -> MWProject {
        struct Body: Codable { let sectionIds: [String]; enum CodingKeys: String, CodingKey { case sectionIds = "section_ids" } }
        return try await client.request(method: "PUT", path: "\(basePath)/projects/\(projectId)/sections/reorder", body: Body(sectionIds: sectionIds))
    }

    func acceptProjectSectionRevision(projectId: String, sectionId: String) async throws -> MWProject {
        try await client.request(method: "POST", path: "\(basePath)/projects/\(projectId)/sections/\(sectionId)/accept_revision")
    }

    func rejectProjectSectionRevision(projectId: String, sectionId: String) async throws -> MWProject {
        try await client.request(method: "POST", path: "\(basePath)/projects/\(projectId)/sections/\(sectionId)/reject_revision")
    }

    func createProjectChat(projectId: String, title: String? = nil) async throws -> MWThread {
        struct Body: Codable { let title: String? }
        return try await client.request(method: "POST", path: "\(basePath)/projects/\(projectId)/chats", body: Body(title: title))
    }

    /// AI chat threads in a project visible to the current user (own + shared).
    func listProjectChats(projectId: String) async throws -> [MWThread] {
        try await client.request(method: "GET", path: "\(basePath)/projects/\(projectId)/chats")
    }

    /// Share a project thread with another collaborator (owner-only server-side).
    func addThreadCollaborator(threadId: String, userId: String) async throws {
        struct Body: Codable { let user_id: String }
        _ = try await client.requestData(method: "POST", path: "\(basePath)/threads/\(threadId)/collaborators", body: Body(user_id: userId))
    }

    func exportProject(projectId: String, format: String) async throws -> Data {
        try await client.requestData(method: "GET", path: "\(basePath)/projects/\(projectId)/export/\(format)")
    }

    // MARK: - Discipline workflow

    struct MWDisciplineEmployeePatch: Codable {
        var name: String?
        var title: String?
        var department: String?
        var manager_name: String?
        var manager_email: String?
        var employee_email: String?
    }

    struct MWDisciplineInfractionPatch: Codable {
        var category: String?
        var category_label: String?
        var occurred_on: String?
        var summary: String?
        var severity: String?
    }

    struct MWDisciplinePatch: Codable {
        var employee: MWDisciplineEmployeePatch?
        var infraction: MWDisciplineInfractionPatch?
        var level: String?
    }

    func patchDiscipline(projectId: String, patch: MWDisciplinePatch) async throws -> MWProject {
        try await client.request(method: "PATCH", path: "\(basePath)/projects/\(projectId)/discipline", body: patch)
    }

    func markDisciplineMeetingHeld(projectId: String) async throws -> MWProject {
        try await client.request(method: "POST", path: "\(basePath)/projects/\(projectId)/discipline/meeting-held")
    }

    func requestDisciplineSignature(projectId: String, employeeEmail: String) async throws -> MWProject {
        struct Body: Codable { let employee_email: String }
        return try await client.request(
            method: "POST",
            path: "\(basePath)/projects/\(projectId)/discipline/signature/request",
            body: Body(employee_email: employeeEmail),
        )
    }

    func refuseDisciplineSignature(projectId: String, notes: String) async throws -> MWProject {
        struct Body: Codable { let notes: String }
        return try await client.request(
            method: "POST",
            path: "\(basePath)/projects/\(projectId)/discipline/signature/refuse",
            body: Body(notes: notes),
        )
    }

    func uploadDisciplinePhysicalSignature(projectId: String, fileURL: URL) async throws -> MWProject {
        let data = try Data(contentsOf: fileURL)
        let filename = fileURL.lastPathComponent
        var multipart = MultipartUploadBuilder()
        multipart.addFile(name: "file", filename: filename, mimeType: "application/pdf", data: data)
        let (body, contentType) = multipart.finalize()

        guard let url = URL(string: "\(client.baseURL)\(basePath)/projects/\(projectId)/discipline/signature/upload-physical") else {
            throw APIError.invalidURL
        }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue(contentType, forHTTPHeaderField: "Content-Type")
        if let token = client.accessToken {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        request.httpBody = body

        let (responseData, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
            let code = (response as? HTTPURLResponse)?.statusCode ?? 0
            throw APIError.httpError(code, "Upload failed")
        }
        return try JSONDecoder().decode(MWProject.self, from: responseData)
    }

    // MARK: - Project Invites

    func listPendingInvites() async throws -> [MWProjectInvite] {
        try await client.request(method: "GET", path: "\(basePath)/project-invites")
    }

    func acceptProjectInvite(projectId: String) async throws {
        _ = try await client.requestData(method: "POST", path: "\(basePath)/projects/\(projectId)/invite/accept")
        invalidateProjectLists()
    }

    func declineProjectInvite(projectId: String) async throws {
        _ = try await client.requestData(method: "POST", path: "\(basePath)/projects/\(projectId)/invite/decline")
        invalidateProjectLists()
    }
}
