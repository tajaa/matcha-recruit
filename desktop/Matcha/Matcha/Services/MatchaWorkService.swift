import Foundation

private extension Data {
    mutating func append(_ string: String) {
        if let d = string.data(using: .utf8) { append(d) }
    }
}

private struct MWCacheEntry<Value> {
    let value: Value
    let expiresAt: Date

    var isValid: Bool {
        expiresAt > Date()
    }
}

class MatchaWorkService {
    static let shared = MatchaWorkService()
    private let client = APIClient.shared
    private let basePath = "/matcha-work"
    private let cacheTTL: TimeInterval = 60
    private var cacheScope: String?
    private var threadListCache: [String: MWCacheEntry<[MWThread]>] = [:]
    private var threadDetailCache: [String: MWCacheEntry<MWThreadDetail>] = [:]
    private var versionsCache: [String: MWCacheEntry<[MWDocumentVersion]>] = [:]
    private var pdfCache: [String: MWCacheEntry<Data>] = [:]
    private var projectListCache: [String: MWCacheEntry<[MWProject]>] = [:]
    private init() {}

    private func cachedValue<Value>(_ entry: MWCacheEntry<Value>?) -> Value? {
        guard let entry else { return nil }
        guard entry.isValid else { return nil }
        return entry.value
    }

    private func makeListCacheKey(status: String?) -> String {
        status ?? "__all__"
    }

    private func makePDFCacheKey(threadId: String, version: Int?) -> String {
        "\(threadId):\(version.map(String.init) ?? "latest")"
    }

    func updateCacheScope(_ scope: String?) {
        guard cacheScope != scope else { return }
        cacheScope = scope
        clearCaches()
    }

    func clearCaches() {
        threadListCache.removeAll()
        threadDetailCache.removeAll()
        versionsCache.removeAll()
        pdfCache.removeAll()
        projectListCache.removeAll()
    }

    /// Drop cached project lists. Call when project membership in any status
    /// bucket changes (create / delete / status change).
    func invalidateProjectLists() {
        projectListCache.removeAll()
    }

    func invalidateThread(threadId: String) {
        threadDetailCache.removeValue(forKey: threadId)
        versionsCache.removeValue(forKey: threadId)
        pdfCache = pdfCache.filter { !$0.key.hasPrefix("\(threadId):") }
        // Don't wipe threadListCache here — sidebar still has accurate data in
        // its own ViewModel state. Stale cache entries expire on TTL (60s).
        // Listings only need a hard refresh on create/delete/archive/pin/title,
        // which call into the dedicated invalidators below.
    }

    /// Drop the cached thread lists. Call when thread membership in any
    /// status bucket changes (create, delete, archive, pin, title rename).
    func invalidateThreadLists() {
        threadListCache.removeAll()
    }

    func listThreads(status: String? = nil, forceRefresh: Bool = false) async throws -> [MWThread] {
        let cacheKey = makeListCacheKey(status: status)
        if !forceRefresh, let cached = cachedValue(threadListCache[cacheKey]) {
            return cached
        }

        var path = "\(basePath)/threads?limit=50"
        if let status = status { path += "&status=\(status)" }
        let threads: [MWThread] = try await client.request(method: "GET", path: path)
        threadListCache[cacheKey] = MWCacheEntry(
            value: threads,
            expiresAt: Date().addingTimeInterval(cacheTTL)
        )
        return threads
    }

    func getThread(id: String, forceRefresh: Bool = false) async throws -> MWThreadDetail {
        if !forceRefresh, let cached = cachedValue(threadDetailCache[id]) {
            return cached
        }

        let detail: MWThreadDetail = try await client.request(method: "GET", path: "\(basePath)/threads/\(id)")
        threadDetailCache[id] = MWCacheEntry(
            value: detail,
            expiresAt: Date().addingTimeInterval(cacheTTL)
        )
        return detail
    }

    func createThread(title: String?, initialMessage: String?) async throws -> MWThread {
        let body = MWCreateThreadRequest(title: title, initialMessage: initialMessage)
        let response: MWCreateThreadResponse = try await client.request(method: "POST", path: "\(basePath)/threads", body: body)
        invalidateThreadLists()
        return response.toThread()
    }

    func deleteThread(id: String) async throws {
        _ = try await client.requestData(method: "DELETE", path: "\(basePath)/threads/\(id)")
        invalidateThread(threadId: id)
        invalidateThreadLists()
    }

    func setPinned(id: String, pinned: Bool) async throws -> MWThread {
        let body = MWPinRequest(pinned: pinned)
        let thread: MWThread = try await client.request(
            method: "POST",
            path: "\(basePath)/threads/\(id)/pin",
            body: body
        )
        invalidateThread(threadId: id)
        invalidateThreadLists()
        return thread
    }

    func getVersions(threadId: String, forceRefresh: Bool = false) async throws -> [MWDocumentVersion] {
        if !forceRefresh, let cached = cachedValue(versionsCache[threadId]) {
            return cached
        }

        let versions: [MWDocumentVersion] = try await client.request(
            method: "GET",
            path: "\(basePath)/threads/\(threadId)/versions"
        )
        versionsCache[threadId] = MWCacheEntry(
            value: versions,
            expiresAt: Date().addingTimeInterval(cacheTTL)
        )
        return versions
    }

    func revertThread(id: String, version: Int) async throws -> MWSendMessageResponse {
        let body = MWRevertRequest(version: version)
        let response: MWSendMessageResponse = try await client.request(
            method: "POST",
            path: "\(basePath)/threads/\(id)/revert",
            body: body
        )
        invalidateThread(threadId: id)
        return response
    }

    func finalizeThread(id: String) async throws -> MWFinalizeResponse {
        let response: MWFinalizeResponse = try await client.request(
            method: "POST",
            path: "\(basePath)/threads/\(id)/finalize"
        )
        invalidateThread(threadId: id)
        invalidateThreadLists()
        return response
    }

    func getPDFData(threadId: String, version: Int? = nil, forceRefresh: Bool = false) async throws -> Data {
        let cacheKey = makePDFCacheKey(threadId: threadId, version: version)
        if !forceRefresh, let cached = cachedValue(pdfCache[cacheKey]) {
            return cached
        }

        var path = "\(basePath)/threads/\(threadId)/pdf"
        if let v = version { path += "?version=\(v)" }
        // Step 1: get the signed URL from the backend
        let response: PDFResponse = try await client.request(method: "GET", path: path)
        // Step 2: download the actual PDF bytes from the CDN URL
        guard let url = URL(string: response.pdfUrl) else { throw APIError.invalidURL }
        let (data, _) = try await URLSession.shared.data(from: url)
        pdfCache[cacheKey] = MWCacheEntry(
            value: data,
            expiresAt: Date().addingTimeInterval(cacheTTL)
        )
        return data
    }

    private struct PDFResponse: Decodable {
        let pdfUrl: String
        enum CodingKeys: String, CodingKey { case pdfUrl = "pdf_url" }
    }

    func getPresentationPdfUrl(threadId: String) async throws -> String {
        let response: PDFResponse = try await client.request(
            method: "GET",
            path: "\(basePath)/threads/\(threadId)/presentation/pdf"
        )
        return response.pdfUrl
    }

    func uploadImages(
        threadId: String,
        images: [(data: Data, filename: String, mimeType: String)]
    ) async throws -> [String] {
        let boundary = "Boundary-\(UUID().uuidString)"
        var body = Data()
        for image in images {
            body.append("--\(boundary)\r\n")
            body.append("Content-Disposition: form-data; name=\"files\"; filename=\"\(image.filename)\"\r\n")
            body.append("Content-Type: \(image.mimeType)\r\n\r\n")
            body.append(image.data)
            body.append("\r\n")
        }
        body.append("--\(boundary)--\r\n")

        guard let url = URL(string: "\(client.baseURL)\(basePath)/threads/\(threadId)/images") else {
            throw APIError.invalidURL
        }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        if let token = client.accessToken {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        request.httpBody = body

        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
            let msg = String(data: data, encoding: .utf8) ?? "Upload failed"
            throw APIError.httpError((response as? HTTPURLResponse)?.statusCode ?? 0, msg)
        }
        struct ImagesResponse: Decodable { let images: [String] }
        let images = try JSONDecoder().decode(ImagesResponse.self, from: data).images
        invalidateThread(threadId: threadId)
        return images
    }

    // MARK: - Mode Toggles

    func setNodeMode(threadId: String, enabled: Bool) async throws -> MWThread {
        let body = MWNodeModeRequest(nodeMode: enabled)
        let thread: MWThread = try await client.request(
            method: "POST",
            path: "\(basePath)/threads/\(threadId)/node-mode",
            body: body
        )
        invalidateThread(threadId: threadId)
        return thread
    }

    func setComplianceMode(threadId: String, enabled: Bool) async throws -> MWThread {
        let body = MWComplianceModeRequest(complianceMode: enabled)
        let thread: MWThread = try await client.request(
            method: "POST",
            path: "\(basePath)/threads/\(threadId)/compliance-mode",
            body: body
        )
        invalidateThread(threadId: threadId)
        return thread
    }

    func setPayerMode(threadId: String, enabled: Bool) async throws -> MWThread {
        let body = MWPayerModeRequest(payerMode: enabled)
        let thread: MWThread = try await client.request(
            method: "POST",
            path: "\(basePath)/threads/\(threadId)/payer-mode",
            body: body
        )
        invalidateThread(threadId: threadId)
        return thread
    }

    // MARK: - Title & Archive

    func updateTitle(threadId: String, title: String) async throws -> MWThread {
        let body = MWUpdateTitleRequest(title: title)
        let thread: MWThread = try await client.request(
            method: "PATCH",
            path: "\(basePath)/threads/\(threadId)",
            body: body
        )
        invalidateThread(threadId: threadId)
        invalidateThreadLists()
        return thread
    }

    func archiveThread(id: String) async throws {
        _ = try await client.requestData(method: "DELETE", path: "\(basePath)/threads/\(id)")
        invalidateThread(threadId: id)
        invalidateThreadLists()
    }

    func unarchiveThread(id: String) async throws {
        _ = try await client.requestData(method: "POST", path: "\(basePath)/threads/\(id)/unarchive")
        invalidateThread(threadId: id)
        invalidateThreadLists()
    }

    // MARK: - Resume / Inventory File Upload (multipart)

    func uploadFiles(
        threadId: String,
        endpoint: String,
        files: [(data: Data, filename: String, mimeType: String)]
    ) async throws -> URLSession.AsyncBytes {
        let boundary = "Boundary-\(UUID().uuidString)"
        var body = Data()
        for file in files {
            body.append("--\(boundary)\r\n")
            body.append("Content-Disposition: form-data; name=\"files\"; filename=\"\(file.filename)\"\r\n")
            body.append("Content-Type: \(file.mimeType)\r\n\r\n")
            body.append(file.data)
            body.append("\r\n")
        }
        body.append("--\(boundary)--\r\n")

        guard let url = URL(string: "\(client.baseURL)\(basePath)/threads/\(threadId)/\(endpoint)") else {
            throw APIError.invalidURL
        }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        request.setValue("text/event-stream", forHTTPHeaderField: "Accept")
        if let token = client.accessToken {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        request.httpBody = body

        let (bytes, response) = try await URLSession.shared.bytes(for: request)
        guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
            throw APIError.httpError((response as? HTTPURLResponse)?.statusCode ?? 0, "Upload failed")
        }
        invalidateThread(threadId: threadId)
        return bytes
    }

    // MARK: - Send / Sync Interviews

    func sendInterviews(
        threadId: String,
        candidateIds: [String],
        positionTitle: String? = nil,
        customMessage: String? = nil
    ) async throws -> [String: Any] {
        let body = MWSendInterviewsRequest(
            candidateIds: candidateIds,
            positionTitle: positionTitle,
            customMessage: customMessage
        )
        let data = try await client.requestData(
            method: "POST",
            path: "\(basePath)/threads/\(threadId)/resume/send-interviews",
            body: body
        )
        invalidateThread(threadId: threadId)
        let json = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] ?? [:]
        return json
    }

    func syncInterviews(threadId: String) async throws {
        _ = try await client.requestData(
            method: "POST",
            path: "\(basePath)/threads/\(threadId)/resume/sync-interviews"
        )
        invalidateThread(threadId: threadId)
    }

    // MARK: - Usage Summary

    func fetchUsageSummary(periodDays: Int = 30) async throws -> MWUsageSummary {
        try await client.request(
            method: "GET",
            path: "\(basePath)/usage/summary?period_days=\(periodDays)"
        )
    }

    // MARK: - Presence

    func sendHeartbeat() async throws {
        _ = try await client.requestData(method: "POST", path: "\(basePath)/presence/heartbeat")
    }

    func fetchOnlineUsers() async throws -> [MWOnlineUser] {
        try await client.request(method: "GET", path: "\(basePath)/presence/online")
    }

    // MARK: - Collab Discussion Channel

    func ensureProjectDiscussionChannel(projectId: String) async throws -> String {
        struct Res: Codable { let channel_id: String }
        let res: Res = try await client.request(
            method: "POST",
            path: "\(basePath)/projects/\(projectId)/discussion-channel"
        )
        return res.channel_id
    }

    // MARK: - Notifications

    func fetchNotifications(unreadOnly: Bool = false, limit: Int = 30) async throws -> [MWAppNotification] {
        struct Res: Codable { let notifications: [MWAppNotification] }
        let path = "\(basePath)/notifications?limit=\(limit)&unread_only=\(unreadOnly)"
        let res: Res = try await client.request(method: "GET", path: path)
        return res.notifications
    }

    func fetchNotificationsUnreadCount() async throws -> Int {
        struct Res: Codable { let unread_count: Int }
        let res: Res = try await client.request(method: "GET", path: "\(basePath)/notifications/unread-count")
        return res.unread_count
    }

    func markNotificationsRead(ids: [String]) async throws {
        struct Body: Encodable { let notification_ids: [String] }
        _ = try await client.requestData(
            method: "POST",
            path: "\(basePath)/notifications/mark-read",
            body: Body(notification_ids: ids)
        )
    }

    func markAllNotificationsRead() async throws {
        _ = try await client.requestData(method: "POST", path: "\(basePath)/notifications/mark-all-read")
    }

    // MARK: - Review Requests

    func sendReviewRequests(
        threadId: String,
        emails: [String],
        customMessage: String? = nil
    ) async throws -> MWSendReviewRequestsResponse {
        let body = MWSendReviewRequestsRequest(recipientEmails: emails, customMessage: customMessage)
        return try await client.request(
            method: "POST",
            path: "\(basePath)/threads/\(threadId)/review-requests/send",
            body: body
        )
    }

    // MARK: - Export

    func exportThread(threadId: String, format: String) async throws -> Data {
        try await client.requestData(
            method: "GET",
            path: "\(basePath)/threads/\(threadId)/project/export/\(format)"
        )
    }

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

    func createProject(title: String, projectType: String = "general") async throws -> MWProject {
        struct Body: Codable { let title: String; let projectType: String
            enum CodingKeys: String, CodingKey { case title; case projectType = "project_type" }
        }
        let project: MWProject = try await client.request(method: "POST", path: "\(basePath)/projects", body: Body(title: title, projectType: projectType))
        invalidateProjectLists()
        return project
    }

    func getProjectDetail(id: String) async throws -> MWProject {
        try await client.request(method: "GET", path: "\(basePath)/projects/\(id)")
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
    func updateProjectMeta(id: String, title: String? = nil, isPinned: Bool? = nil, status: String? = nil) async throws -> MWProject {
        defer { invalidateProjectLists() }
        struct Body: Codable { let title: String?; let isPinned: Bool?; let status: String?
            enum CodingKeys: String, CodingKey { case title; case isPinned = "is_pinned"; case status }
        }
        return try await client.request(method: "PATCH", path: "\(basePath)/projects/\(id)", body: Body(title: title, isPinned: isPinned, status: status))
    }

    func archiveProject(id: String) async throws {
        _ = try await client.requestData(method: "DELETE", path: "\(basePath)/projects/\(id)")
        invalidateProjectLists()
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
        let boundary = "Boundary-\(UUID().uuidString)"
        var body = Data()
        body.append("--\(boundary)\r\n")
        body.append("Content-Disposition: form-data; name=\"file\"; filename=\"\(filename)\"\r\n")
        body.append("Content-Type: application/pdf\r\n\r\n")
        body.append(data)
        body.append("\r\n--\(boundary)--\r\n")

        guard let url = URL(string: "\(client.baseURL)\(basePath)/projects/\(projectId)/discipline/signature/upload-physical") else {
            throw APIError.invalidURL
        }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
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

    // MARK: - Collaborators

    func listCollaborators(projectId: String) async throws -> [MWProjectCollaborator] {
        try await client.request(method: "GET", path: "\(basePath)/projects/\(projectId)/collaborators")
    }

    func addCollaborator(projectId: String, userId: String) async throws {
        struct Body: Codable { let userId: String; let role: String; enum CodingKeys: String, CodingKey { case userId = "user_id"; case role } }
        _ = try await client.requestData(method: "POST", path: "\(basePath)/projects/\(projectId)/collaborators", body: Body(userId: userId, role: "collaborator"))
    }

    func removeCollaborator(projectId: String, userId: String) async throws {
        _ = try await client.requestData(method: "DELETE", path: "\(basePath)/projects/\(projectId)/collaborators/\(userId)")
    }

    func searchAdminUsers(query: String) async throws -> [MWAdminSearchUser] {
        let encoded = query.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? query
        return try await client.request(method: "GET", path: "\(basePath)/admin-users/search?q=\(encoded)")
    }

    func searchInvitableUsers(query: String) async throws -> [MWAdminSearchUser] {
        // urlQueryAllowed leaves "+", "&", "=" unencoded which breaks emails
        // like "user+tag@gmail.com" — Starlette decodes "+" as a space.
        var allowed = CharacterSet.urlQueryAllowed
        allowed.remove(charactersIn: "+&=#?")
        let encoded = query.addingPercentEncoding(withAllowedCharacters: allowed) ?? query
        return try await client.request(method: "GET", path: "/channels/invitable-users?q=\(encoded)")
    }

    // MARK: - Project-scoped kanban tasks (collab projects)

    func listProjectTasks(projectId: String) async throws -> [MWProjectTask] {
        try await client.request(method: "GET", path: "\(basePath)/projects/\(projectId)/tasks")
    }

    func createProjectTask(
        projectId: String,
        title: String,
        boardColumn: String = "todo",
        description: String? = nil,
        priority: String = "medium",
        dueDate: String? = nil,
        assignedTo: String? = nil
    ) async throws -> MWProjectTask {
        struct Body: Encodable {
            let title: String
            let description: String?
            let board_column: String
            let priority: String
            let due_date: String?
            let assigned_to: String?
        }
        return try await client.request(
            method: "POST",
            path: "\(basePath)/projects/\(projectId)/tasks",
            body: Body(
                title: title, description: description, board_column: boardColumn,
                priority: priority, due_date: dueDate, assigned_to: assignedTo
            )
        )
    }

    struct ProjectTaskPatch: Encodable {
        var title: String?
        var description: String?
        var boardColumn: String?
        var priority: String?
        var status: String?
        var dueDate: String?
        var assignedTo: String?

        enum CodingKeys: String, CodingKey {
            case title, description, priority, status
            case boardColumn = "board_column"
            case dueDate = "due_date"
            case assignedTo = "assigned_to"
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
            try c.encodeIfPresent(priority, forKey: .priority)
            try c.encodeIfPresent(status, forKey: .status)
            try c.encodeIfPresent(dueDate, forKey: .dueDate)
            try c.encodeIfPresent(assignedTo, forKey: .assignedTo)
        }
    }

    func updateProjectTask(
        projectId: String,
        taskId: String,
        patch: ProjectTaskPatch
    ) async throws -> MWProjectTask {
        try await client.request(
            method: "PATCH",
            path: "\(basePath)/projects/\(projectId)/tasks/\(taskId)",
            body: patch
        )
    }

    func deleteProjectTask(projectId: String, taskId: String) async throws {
        _ = try await client.requestData(
            method: "DELETE",
            path: "\(basePath)/projects/\(projectId)/tasks/\(taskId)"
        )
    }

    func markProjectComplete(projectId: String) async throws {
        _ = try await client.requestData(
            method: "POST",
            path: "\(basePath)/projects/\(projectId)/complete"
        )
    }

    // MARK: - Project files

    func listProjectFiles(projectId: String) async throws -> [MWProjectFile] {
        try await client.request(method: "GET", path: "\(basePath)/projects/\(projectId)/files")
    }

    func uploadProjectFile(
        projectId: String,
        file: (data: Data, filename: String, mimeType: String)
    ) async throws -> MWProjectFile {
        let boundary = "Boundary-\(UUID().uuidString)"
        var body = Data()
        body.append("--\(boundary)\r\n")
        body.append("Content-Disposition: form-data; name=\"file\"; filename=\"\(file.filename)\"\r\n")
        body.append("Content-Type: \(file.mimeType)\r\n\r\n")
        body.append(file.data)
        body.append("\r\n")
        body.append("--\(boundary)--\r\n")

        guard let url = URL(string: "\(client.baseURL)\(basePath)/projects/\(projectId)/files") else {
            throw APIError.invalidURL
        }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
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

    func deleteProjectFile(projectId: String, fileId: String) async throws {
        _ = try await client.requestData(
            method: "DELETE",
            path: "\(basePath)/projects/\(projectId)/files/\(fileId)"
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
        let boundary = "Boundary-\(UUID().uuidString)"
        var body = Data()
        body.append("--\(boundary)\r\n")
        body.append("Content-Disposition: form-data; name=\"file\"; filename=\"\(file.filename)\"\r\n")
        body.append("Content-Type: \(file.mimeType)\r\n\r\n")
        body.append(file.data)
        body.append("\r\n")
        body.append("--\(boundary)--\r\n")

        guard let url = URL(string: "\(client.baseURL)\(basePath)/projects/\(projectId)/blog-media") else {
            throw APIError.invalidURL
        }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
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

    // MARK: - Billing

    func getPersonalSubscription() async throws -> MWSubscription {
        try await client.request(method: "GET", path: "\(basePath)/billing/subscription")
    }

    func startPersonalCheckout(successUrl: String, cancelUrl: String) async throws -> String {
        struct Body: Codable {
            let successUrl: String
            let cancelUrl: String
            enum CodingKeys: String, CodingKey {
                case successUrl = "success_url"
                case cancelUrl = "cancel_url"
            }
        }
        let resp: MWCheckoutResponse = try await client.request(
            method: "POST",
            path: "\(basePath)/billing/checkout/personal",
            body: Body(successUrl: successUrl, cancelUrl: cancelUrl)
        )
        return resp.checkoutUrl
    }

    // MARK: - Recruiting Pipeline

    func updateProjectPosting(projectId: String, posting: [String: Any]) async throws -> Data {
        let json = try JSONSerialization.data(withJSONObject: posting)
        guard let url = URL(string: "\(client.baseURL)\(basePath)/projects/\(projectId)/posting") else { throw APIError.invalidURL }
        var request = URLRequest(url: url)
        request.httpMethod = "PUT"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if let token = client.accessToken { request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization") }
        request.httpBody = json
        let (data, _) = try await URLSession.shared.data(for: request)
        return data
    }

    func toggleShortlist(projectId: String, candidateId: String) async throws -> Data {
        try await client.requestData(method: "POST", path: "\(basePath)/projects/\(projectId)/shortlist/\(candidateId)")
    }

    func toggleProjectDismiss(projectId: String, candidateId: String) async throws -> Data {
        try await client.requestData(method: "POST", path: "\(basePath)/projects/\(projectId)/dismiss/\(candidateId)")
    }

    func sendProjectInterviews(
        projectId: String,
        candidateIds: [String],
        positionTitle: String? = nil,
        customMessage: String? = nil
    ) async throws -> [String: Any] {
        let body = MWSendInterviewsRequest(
            candidateIds: candidateIds,
            positionTitle: positionTitle,
            customMessage: customMessage
        )
        let data = try await client.requestData(
            method: "POST",
            path: "\(basePath)/projects/\(projectId)/resume/send-interviews",
            body: body
        )
        let json = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] ?? [:]
        return json
    }

    func syncProjectInterviews(projectId: String) async throws {
        _ = try await client.requestData(
            method: "POST",
            path: "\(basePath)/projects/\(projectId)/resume/sync-interviews"
        )
    }

    func analyzeProjectCandidates(projectId: String) async throws {
        _ = try await client.requestData(
            method: "POST",
            path: "\(basePath)/projects/\(projectId)/resume/analyze"
        )
    }

    func rejectProjectCandidate(projectId: String, candidateId: String, reason: String?, sendEmail: Bool) async throws {
        struct Body: Encodable {
            let reason: String?
            let sendEmail: Bool
            enum CodingKeys: String, CodingKey { case reason; case sendEmail = "send_email" }
        }
        _ = try await client.requestData(
            method: "POST",
            path: "\(basePath)/projects/\(projectId)/candidates/\(candidateId)/reject",
            body: Body(reason: reason, sendEmail: sendEmail)
        )
    }

    func uploadProjectResumes(
        projectId: String,
        files: [(data: Data, filename: String, mimeType: String)]
    ) async throws -> URLSession.AsyncBytes {
        let boundary = "Boundary-\(UUID().uuidString)"
        var body = Data()
        for file in files {
            body.append("--\(boundary)\r\n")
            body.append("Content-Disposition: form-data; name=\"files\"; filename=\"\(file.filename)\"\r\n")
            body.append("Content-Type: \(file.mimeType)\r\n\r\n")
            body.append(file.data)
            body.append("\r\n")
        }
        body.append("--\(boundary)--\r\n")

        guard let url = URL(string: "\(client.baseURL)\(basePath)/projects/\(projectId)/resume/upload") else {
            throw APIError.invalidURL
        }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        request.setValue("text/event-stream", forHTTPHeaderField: "Accept")
        if let token = client.accessToken {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        request.httpBody = body

        let (bytes, response) = try await URLSession.shared.bytes(for: request)
        guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
            throw APIError.httpError((response as? HTTPURLResponse)?.statusCode ?? 0, "Upload failed")
        }
        return bytes
    }

    // MARK: - Email Agent

    func agentEmailStatus() async throws -> MWAgentEmailStatus {
        try await client.request(method: "GET", path: "\(basePath)/agent/email/status")
    }

    func agentConnectGmail() async throws -> String {
        struct Resp: Codable { let authUrl: String; enum CodingKeys: String, CodingKey { case authUrl = "auth_url" } }
        let resp: Resp = try await client.request(method: "POST", path: "\(basePath)/agent/email/connect")
        return resp.authUrl
    }

    func agentDisconnectGmail() async throws {
        _ = try await client.requestData(method: "DELETE", path: "\(basePath)/agent/email/disconnect")
    }

    func agentFetchEmails() async throws -> [MWAgentEmail] {
        try await client.request(method: "POST", path: "\(basePath)/agent/email/fetch")
    }

    func agentDraftReply(emailId: String, instructions: String) async throws -> String {
        struct Body: Codable { let emailId: String; let instructions: String
            enum CodingKeys: String, CodingKey { case emailId = "email_id"; case instructions }
        }
        struct Resp: Codable { let draft: String }
        let resp: Resp = try await client.request(method: "POST", path: "\(basePath)/agent/email/draft", body: Body(emailId: emailId, instructions: instructions))
        return resp.draft
    }

    func agentSendEmail(to: String, subject: String, body: String, replyToId: String? = nil) async throws {
        struct Body: Codable { let to: String; let subject: String; let body: String; let replyToId: String?
            enum CodingKeys: String, CodingKey { case to, subject, body; case replyToId = "reply_to_id" }
        }
        _ = try await client.requestData(method: "POST", path: "\(basePath)/agent/email/send", body: Body(to: to, subject: subject, body: body, replyToId: replyToId))
    }

    func removeImage(threadId: String, imageUrl: String) async throws -> [String] {
        let encoded = imageUrl.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? imageUrl
        let path = "\(basePath)/threads/\(threadId)/images?url=\(encoded)"
        struct ImagesResponse: Decodable { let images: [String] }
        let result: ImagesResponse = try await client.request(method: "DELETE", path: path)
        invalidateThread(threadId: threadId)
        return result.images
    }

    // MARK: - Blog (project_type == "blog")

    struct BlogCreateBody: Encodable {
        let title: String
        let projectType = "blog"
        let blog: BlogMeta
        struct BlogMeta: Encodable {
            let audience: String
            let tone: String
            let tags: [String]
        }
        enum CodingKeys: String, CodingKey {
            case title, blog
            case projectType = "project_type"
        }
    }

    func createBlog(
        title: String,
        audience: String = "",
        tone: String = "expert-casual",
        tags: [String] = []
    ) async throws -> MWProject {
        let body = BlogCreateBody(title: title, blog: .init(audience: audience, tone: tone, tags: tags))
        return try await client.request(method: "POST", path: "\(basePath)/projects", body: body)
    }

    func patchBlog(id: String, patch: MWBlogPatchRequest) async throws -> MWProject {
        try await client.request(method: "PATCH", path: "\(basePath)/projects/\(id)/blog", body: patch)
    }

    func transitionBlogStatus(id: String, status: String) async throws -> MWProject {
        let body = MWBlogStatusRequest(status: status)
        return try await client.request(method: "POST", path: "\(basePath)/projects/\(id)/blog/status", body: body)
    }
}
