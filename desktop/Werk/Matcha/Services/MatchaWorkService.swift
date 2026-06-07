import Foundation

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
    private var projectDetailCache: [String: MWCacheEntry<MWProject>] = [:]
    // Per-project sub-resource caches (keyed by projectId), so tab- and
    // project-switches paint instantly from cache (stale-while-revalidate)
    // instead of re-fetching 6 endpoints cold every time. Same MWCacheEntry +
    // 60s TTL pattern as projectDetailCache. Populated by the list getters and
    // wholesale by getProjectBundle; invalidated by the matching mutations.
    private var projectTasksCache: [String: MWCacheEntry<[MWProjectTask]>] = [:]
    private var projectFilesCache: [String: MWCacheEntry<[MWProjectFile]>] = [:]
    private var projectFoldersCache: [String: MWCacheEntry<[MWProjectFolder]>] = [:]
    private var projectLinksCache: [String: MWCacheEntry<[MWProjectLink]>] = [:]
    private var projectCollaboratorsCache: [String: MWCacheEntry<[MWProjectCollaborator]>] = [:]
    private var projectElementsCache: [String: MWCacheEntry<[MWProjectElement]>] = [:]
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
        projectDetailCache.removeAll()
        projectTasksCache.removeAll()
        projectFilesCache.removeAll()
        projectFoldersCache.removeAll()
        projectLinksCache.removeAll()
        projectCollaboratorsCache.removeAll()
        projectElementsCache.removeAll()
        JournalService.shared.invalidateLists()
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
        await WorkDetailVMStore.shared.evictThread(id)
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
        var multipart = MultipartUploadBuilder()
        for image in images {
            multipart.addFile(name: "files", filename: image.filename, mimeType: image.mimeType, data: image.data)
        }
        let (body, contentType) = multipart.finalize()

        guard let url = URL(string: "\(client.baseURL)\(basePath)/threads/\(threadId)/images") else {
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
        var multipart = MultipartUploadBuilder()
        for file in files {
            multipart.addFile(name: "files", filename: file.filename, mimeType: file.mimeType, data: file.data)
        }
        let (body, contentType) = multipart.finalize()

        guard let url = URL(string: "\(client.baseURL)\(basePath)/threads/\(threadId)/\(endpoint)") else {
            throw APIError.invalidURL
        }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue(contentType, forHTTPHeaderField: "Content-Type")
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

    // MARK: - Generic Thread File Attachments (multipart)

    /// Upload non-image files to a thread for plain attachment (no analysis).
    /// Returns attachment refs to include on the next message send. The server
    /// stores them + extracts text for AI context only when the user gives an
    /// instruction; a file-only send yields a clarifying reply.
    func uploadThreadFiles(
        threadId: String,
        files: [(data: Data, filename: String, mimeType: String)]
    ) async throws -> [MWMessageAttachment] {
        var multipart = MultipartUploadBuilder()
        for file in files {
            multipart.addFile(name: "files", filename: file.filename, mimeType: file.mimeType, data: file.data)
        }
        let (body, contentType) = multipart.finalize()

        guard let url = URL(string: "\(client.baseURL)\(basePath)/threads/\(threadId)/files") else {
            throw APIError.invalidURL
        }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue(contentType, forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if let token = client.accessToken {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        request.httpBody = body

        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
            throw APIError.httpError((response as? HTTPURLResponse)?.statusCode ?? 0, "Upload failed")
        }
        struct UploadResponse: Decodable { let attachments: [MWMessageAttachment] }
        let decoded = try JSONDecoder().decode(UploadResponse.self, from: data)
        // Server returns kind-less file refs; stamp kind="file" for the client.
        return decoded.attachments.map {
            MWMessageAttachment(url: $0.url, kind: "file", filename: $0.filename,
                                contentType: $0.contentType, size: $0.size)
        }
    }

    // MARK: - Per-message PDF export

    /// Render a single thread message (markdown) to PDF bytes. Lets a plain
    /// thread reply — e.g. a deal memo the AI wrote — be saved as a PDF.
    func exportMessagePDF(threadId: String, messageId: String) async throws -> Data {
        guard let url = URL(string: "\(client.baseURL)\(basePath)/threads/\(threadId)/messages/\(messageId)/export/pdf") else {
            throw APIError.invalidURL
        }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/pdf", forHTTPHeaderField: "Accept")
        if let token = client.accessToken {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
            throw APIError.httpError((response as? HTTPURLResponse)?.statusCode ?? 0, "PDF export failed")
        }
        return data
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

    /// Per-project unread-notification counts for the tab badges.
    func fetchProjectUnreadCounts() async throws -> [String: Int] {
        struct Res: Codable { let counts: [String: Int] }
        let res: Res = try await client.request(
            method: "GET",
            path: "\(basePath)/notifications/project-unread-counts"
        )
        return res.counts
    }

    /// Clear notifications by the entity the user just opened (ticket, note
    /// section, channel). Drops matching rows from the bell and tab badge.
    func markNotificationsReadBy(
        taskId: String? = nil,
        sectionId: String? = nil,
        channelId: String? = nil,
        projectId: String? = nil
    ) async throws {
        struct Body: Encodable {
            let task_id: String?
            let section_id: String?
            let channel_id: String?
            let project_id: String?
        }
        _ = try await client.requestData(
            method: "POST",
            path: "\(basePath)/notifications/mark-read-by",
            body: Body(task_id: taskId, section_id: sectionId, channel_id: channelId, project_id: projectId)
        )
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

    // MARK: - Collaborators

    func cachedCollaborators(_ projectId: String) -> [MWProjectCollaborator]? { cachedValue(projectCollaboratorsCache[projectId]) }
    func invalidateCollaborators(projectId: String) { projectCollaboratorsCache.removeValue(forKey: projectId) }

    func listCollaborators(projectId: String, forceRefresh: Bool = false) async throws -> [MWProjectCollaborator] {
        if !forceRefresh, let cached = cachedValue(projectCollaboratorsCache[projectId]) { return cached }
        let result: [MWProjectCollaborator] = try await client.request(method: "GET", path: "\(basePath)/projects/\(projectId)/collaborators")
        projectCollaboratorsCache[projectId] = MWCacheEntry(value: result, expiresAt: Date().addingTimeInterval(cacheTTL))
        return result
    }

    func addCollaborator(projectId: String, userId: String) async throws {
        struct Body: Codable { let userId: String; let role: String; enum CodingKeys: String, CodingKey { case userId = "user_id"; case role } }
        _ = try await client.requestData(method: "POST", path: "\(basePath)/projects/\(projectId)/collaborators", body: Body(userId: userId, role: "collaborator"))
        invalidateCollaborators(projectId: projectId)
    }

    func removeCollaborator(projectId: String, userId: String) async throws {
        _ = try await client.requestData(method: "DELETE", path: "\(basePath)/projects/\(projectId)/collaborators/\(userId)")
        invalidateCollaborators(projectId: projectId)
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

    func cachedProjectTasks(_ projectId: String) -> [MWProjectTask]? { cachedValue(projectTasksCache[projectId]) }
    func invalidateProjectTasks(projectId: String) { projectTasksCache.removeValue(forKey: projectId) }

    func listProjectTasks(projectId: String, forceRefresh: Bool = false) async throws -> [MWProjectTask] {
        if !forceRefresh, let cached = cachedValue(projectTasksCache[projectId]) { return cached }
        let result: [MWProjectTask] = try await client.request(method: "GET", path: "\(basePath)/projects/\(projectId)/tasks")
        projectTasksCache[projectId] = MWCacheEntry(value: result, expiresAt: Date().addingTimeInterval(cacheTTL))
        return result
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

    // MARK: - Project Elements

    func cachedProjectElements(_ projectId: String) -> [MWProjectElement]? { cachedValue(projectElementsCache[projectId]) }
    func invalidateProjectElements(projectId: String) { projectElementsCache.removeValue(forKey: projectId) }

    func listProjectElements(projectId: String, forceRefresh: Bool = false) async throws -> [MWProjectElement] {
        if !forceRefresh, let cached = cachedValue(projectElementsCache[projectId]) { return cached }
        let result: [MWProjectElement] = try await client.request(method: "GET", path: "\(basePath)/projects/\(projectId)/elements")
        projectElementsCache[projectId] = MWCacheEntry(value: result, expiresAt: Date().addingTimeInterval(cacheTTL))
        return result
    }

    func createProjectElement(
        projectId: String,
        name: String,
        kind: String? = nil,
        description: String? = nil,
        assignedTo: String? = nil
    ) async throws -> MWProjectElement {
        struct Body: Encodable {
            let name: String
            let kind: String?
            let description: String?
            let assigned_to: String?
        }
        defer { invalidateProjectElements(projectId: projectId) }
        return try await client.request(
            method: "POST",
            path: "\(basePath)/projects/\(projectId)/elements",
            body: Body(name: name, kind: kind, description: description, assigned_to: assignedTo)
        )
    }

    func updateProjectElement(
        projectId: String,
        elementId: String,
        name: String? = nil,
        kind: String? = nil,
        description: String? = nil,
        assignedTo: String? = nil,
        repoPaths: [String]? = nil,
        repoBranch: String? = nil
    ) async throws -> MWProjectElement {
        struct Body: Encodable {
            let name: String?
            let kind: String?
            let description: String?
            let assigned_to: String?
            let repo_paths: [String]?
            let repo_branch: String?
        }
        defer { invalidateProjectElements(projectId: projectId) }
        // nil optionals are omitted by JSONEncoder, so only the fields actually
        // passed in get patched. To clear the branch pin pass "" (backend maps
        // falsy → NULL).
        return try await client.request(
            method: "PATCH",
            path: "\(basePath)/projects/\(projectId)/elements/\(elementId)",
            body: Body(name: name, kind: kind, description: description,
                       assigned_to: assignedTo, repo_paths: repoPaths, repo_branch: repoBranch)
        )
    }

    // MARK: - Commit-driven subtask suggestions

    func listCommitSuggestions(projectId: String, taskId: String? = nil) async throws -> [MWCommitSuggestion] {
        var path = "\(basePath)/projects/\(projectId)/commit-suggestions"
        if let taskId { path += "?task_id=\(taskId)" }
        return try await client.request(method: "GET", path: path)
    }

    func acceptCommitSuggestion(projectId: String, suggestionId: String) async throws {
        _ = try await client.requestData(
            method: "POST",
            path: "\(basePath)/projects/\(projectId)/commit-suggestions/\(suggestionId)/accept"
        )
    }

    func dismissCommitSuggestion(projectId: String, suggestionId: String) async throws {
        _ = try await client.requestData(
            method: "POST",
            path: "\(basePath)/projects/\(projectId)/commit-suggestions/\(suggestionId)/dismiss"
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

    // MARK: - GitHub connection

    func getGitHubConnection(projectId: String) async throws -> GitHubConnection {
        try await client.request(method: "GET", path: "\(basePath)/projects/\(projectId)/github/connection")
    }

    /// Connect/change the project's GitHub repo (validated server-side). Empty
    /// repo disconnects.
    func setGitHubConnection(projectId: String, repo: String, branch: String?) async throws -> GitHubConnection {
        struct Body: Encodable { let repo: String; let branch: String? }
        return try await client.request(
            method: "PUT",
            path: "\(basePath)/projects/\(projectId)/github/connection",
            body: Body(repo: repo, branch: branch)
        )
    }

    /// Pull every bound element's code from GitHub (read-only token, server-side)
    /// into its snapshot. No local clone / bookmark needed.
    func syncFromGitHub(projectId: String) async throws -> GitHubSyncResult {
        struct EmptyBody: Encodable {}
        return try await client.request(
            method: "POST",
            path: "\(basePath)/projects/\(projectId)/github/sync",
            body: EmptyBody()
        )
    }

    /// Pull commits from GitHub (no local git) → commit→subtask matcher →
    /// suggestions on tickets. `force` re-scans recent commits (manual button);
    /// otherwise only NEW commits since the last scan (watermark). Returns
    /// (commits evaluated, pending list).
    func scanCommitsFromGitHub(projectId: String, force: Bool = false) async throws -> (scanned: Int, suggestions: [MWCommitSuggestion]) {
        struct Body: Encodable { let force: Bool }
        struct Resp: Decodable { let scanned: Int; let suggestions: [MWCommitSuggestion] }
        let r: Resp = try await client.request(
            method: "POST",
            path: "\(basePath)/projects/\(projectId)/github/scan-commits",
            body: Body(force: force)
        )
        return (r.scanned, r.suggestions)
    }

    /// Register a GitHub push webhook on the connected repo so a merge triggers a
    /// scan automatically (no polling). Returns true if installed/already present.
    @discardableResult
    func installGitHubWebhook(projectId: String) async throws -> Bool {
        struct EmptyBody: Encodable {}
        struct Resp: Decodable { let installed: Bool? }
        let r: Resp = try await client.request(
            method: "POST",
            path: "\(basePath)/projects/\(projectId)/github/webhook/install",
            body: EmptyBody()
        )
        return r.installed ?? false
    }

    // MARK: - Prop draft tickets

    func listTicketDrafts(projectId: String, status: String? = nil) async throws -> [MWTicketDraft] {
        var path = "\(basePath)/projects/\(projectId)/ticket-drafts"
        if let status { path += "?status=\(status)" }
        return try await client.request(method: "GET", path: path)
    }

    func createTicketDraft(projectId: String, kind: String, title: String? = nil, elementId: String? = nil) async throws -> MWTicketDraft {
        struct Body: Encodable { let kind: String; let title: String?; let element_id: String? }
        return try await client.request(
            method: "POST",
            path: "\(basePath)/projects/\(projectId)/ticket-drafts",
            body: Body(kind: kind, title: title, element_id: elementId)
        )
    }

    func getTicketDraft(projectId: String, draftId: String) async throws -> MWTicketDraft {
        try await client.request(method: "GET", path: "\(basePath)/projects/\(projectId)/ticket-drafts/\(draftId)")
    }

    struct TicketDraftPatch: Encodable {
        var kind: String?
        var title: String?
        var description: String?
        var priority: String?
        var element_id: String?
        var status: String?
        var draft_subtasks: [String]?
    }

    func updateTicketDraft(projectId: String, draftId: String, patch: TicketDraftPatch) async throws -> MWTicketDraft {
        try await client.request(
            method: "PATCH",
            path: "\(basePath)/projects/\(projectId)/ticket-drafts/\(draftId)",
            body: patch
        )
    }

    func deleteTicketDraft(projectId: String, draftId: String) async throws {
        _ = try await client.requestData(
            method: "DELETE",
            path: "\(basePath)/projects/\(projectId)/ticket-drafts/\(draftId)"
        )
    }

    func listPropMessages(projectId: String, draftId: String) async throws -> [MWPropMessage] {
        try await client.request(method: "GET", path: "\(basePath)/projects/\(projectId)/ticket-drafts/\(draftId)/messages")
    }

    func postPropMessage(projectId: String, draftId: String, content: String) async throws -> MWPropChatTurn {
        struct Body: Encodable { let content: String }
        return try await client.request(
            method: "POST",
            path: "\(basePath)/projects/\(projectId)/ticket-drafts/\(draftId)/messages",
            body: Body(content: content)
        )
    }

    func generateDraftFields(projectId: String, draftId: String) async throws -> MWTicketDraft {
        try await client.request(
            method: "POST",
            path: "\(basePath)/projects/\(projectId)/ticket-drafts/\(draftId)/generate"
        )
    }

    struct PromoteOverrides: Encodable {
        var title: String?
        var description: String?
        var priority: String?
        var category: String?
        var board_column: String?
        var element_id: String?
        var assigned_to: String?
        var subtasks: [String]?
    }

    func promoteDraft(projectId: String, draftId: String, overrides: PromoteOverrides) async throws -> MWProjectTask {
        try await client.request(
            method: "POST",
            path: "\(basePath)/projects/\(projectId)/ticket-drafts/\(draftId)/promote",
            body: overrides
        )
    }

    func deleteProjectElement(projectId: String, elementId: String) async throws {
        _ = try await client.requestData(
            method: "DELETE",
            path: "\(basePath)/projects/\(projectId)/elements/\(elementId)"
        )
        invalidateProjectElements(projectId: projectId)
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

    // MARK: - Project files

    func cachedProjectFiles(_ projectId: String) -> [MWProjectFile]? { cachedValue(projectFilesCache[projectId]) }
    func invalidateProjectFiles(projectId: String) { projectFilesCache.removeValue(forKey: projectId) }

    func listProjectFiles(projectId: String, forceRefresh: Bool = false) async throws -> [MWProjectFile] {
        if !forceRefresh, let cached = cachedValue(projectFilesCache[projectId]) { return cached }
        let result: [MWProjectFile] = try await client.request(method: "GET", path: "\(basePath)/projects/\(projectId)/files")
        projectFilesCache[projectId] = MWCacheEntry(value: result, expiresAt: Date().addingTimeInterval(cacheTTL))
        return result
    }

    func cachedProjectLinks(_ projectId: String) -> [MWProjectLink]? { cachedValue(projectLinksCache[projectId]) }
    func invalidateProjectLinks(projectId: String) { projectLinksCache.removeValue(forKey: projectId) }

    /// Links shared in the project's collab chat (URLs pulled from messages).
    func listProjectLinks(projectId: String, forceRefresh: Bool = false) async throws -> [MWProjectLink] {
        if !forceRefresh, let cached = cachedValue(projectLinksCache[projectId]) { return cached }
        let result: [MWProjectLink] = try await client.request(method: "GET", path: "\(basePath)/projects/\(projectId)/links")
        projectLinksCache[projectId] = MWCacheEntry(value: result, expiresAt: Date().addingTimeInterval(cacheTTL))
        return result
    }

    /// Backfill Files/Media with all discussion-chat attachments (idempotent).
    /// Returns the number of newly-added files.
    @discardableResult
    func syncChatFiles(projectId: String) async throws -> Int {
        struct Resp: Decodable { let added: Int }
        let r: Resp = try await client.request(
            method: "POST",
            path: "\(basePath)/projects/\(projectId)/files/sync-chat"
        )
        // Server may have added file rows and surfaced new chat links.
        invalidateProjectFiles(projectId: projectId)
        invalidateProjectLinks(projectId: projectId)
        return r.added
    }

    func uploadProjectFile(
        projectId: String,
        file: (data: Data, filename: String, mimeType: String)
    ) async throws -> MWProjectFile {
        defer { invalidateProjectFiles(projectId: projectId) }
        var multipart = MultipartUploadBuilder()
        multipart.addFile(name: "file", filename: file.filename, mimeType: file.mimeType, data: file.data)
        let (body, contentType) = multipart.finalize()

        guard let url = URL(string: "\(client.baseURL)\(basePath)/projects/\(projectId)/files") else {
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

    func deleteProjectFile(projectId: String, fileId: String) async throws {
        _ = try await client.requestData(
            method: "DELETE",
            path: "\(basePath)/projects/\(projectId)/files/\(fileId)"
        )
        invalidateProjectFiles(projectId: projectId)
    }

    // MARK: - Project file folders

    func cachedProjectFolders(_ projectId: String) -> [MWProjectFolder]? { cachedValue(projectFoldersCache[projectId]) }
    func invalidateProjectFolders(projectId: String) { projectFoldersCache.removeValue(forKey: projectId) }

    func listProjectFolders(projectId: String, forceRefresh: Bool = false) async throws -> [MWProjectFolder] {
        if !forceRefresh, let cached = cachedValue(projectFoldersCache[projectId]) { return cached }
        let result: [MWProjectFolder] = try await client.request(method: "GET", path: "\(basePath)/projects/\(projectId)/folders")
        projectFoldersCache[projectId] = MWCacheEntry(value: result, expiresAt: Date().addingTimeInterval(cacheTTL))
        return result
    }

    func createProjectFolder(projectId: String, name: String, parentId: String? = nil) async throws -> MWProjectFolder {
        struct Body: Encodable { let name: String; let parent_id: String? }
        defer { invalidateProjectFolders(projectId: projectId) }
        return try await client.request(
            method: "POST",
            path: "\(basePath)/projects/\(projectId)/folders",
            body: Body(name: name, parent_id: parentId)
        )
    }

    func renameProjectFolder(projectId: String, folderId: String, name: String) async throws -> MWProjectFolder {
        struct Body: Encodable { let name: String }
        defer { invalidateProjectFolders(projectId: projectId) }
        return try await client.request(
            method: "PATCH",
            path: "\(basePath)/projects/\(projectId)/folders/\(folderId)",
            body: Body(name: name)
        )
    }

    func deleteProjectFolder(projectId: String, folderId: String) async throws {
        _ = try await client.requestData(
            method: "DELETE",
            path: "\(basePath)/projects/\(projectId)/folders/\(folderId)"
        )
        // Server re-parents the folder's files to root (folder_id SET NULL),
        // so the files list changes too.
        invalidateProjectFolders(projectId: projectId)
        invalidateProjectFiles(projectId: projectId)
    }

    /// Move a file into a folder, or to the root when folderId is nil.
    func moveProjectFile(projectId: String, fileId: String, folderId: String?) async throws -> MWProjectFile {
        struct Body: Encodable { let folder_id: String? }
        defer { invalidateProjectFiles(projectId: projectId) }
        return try await client.request(
            method: "PATCH",
            path: "\(basePath)/projects/\(projectId)/files/\(fileId)",
            body: Body(folder_id: folderId)
        )
    }

    /// Copy a file into a folder, leaving the original at root (Media "Add to Files").
    func copyProjectFile(projectId: String, fileId: String, folderId: String) async throws -> MWProjectFile {
        struct Body: Encodable { let folder_id: String }
        defer { invalidateProjectFiles(projectId: projectId) }
        return try await client.request(
            method: "POST",
            path: "\(basePath)/projects/\(projectId)/files/\(fileId)/copy",
            body: Body(folder_id: folderId)
        )
    }

    // MARK: - Element context repository (files / folders / notes)

    func listElementFiles(projectId: String, elementId: String) async throws -> [MWProjectFile] {
        try await client.request(method: "GET", path: "\(basePath)/projects/\(projectId)/elements/\(elementId)/files")
    }

    func listElementFolders(projectId: String, elementId: String) async throws -> [MWProjectFolder] {
        try await client.request(method: "GET", path: "\(basePath)/projects/\(projectId)/elements/\(elementId)/folders")
    }

    func createElementFolder(projectId: String, elementId: String, name: String, parentId: String? = nil) async throws -> MWProjectFolder {
        struct Body: Encodable { let name: String; let parent_id: String? }
        return try await client.request(
            method: "POST",
            path: "\(basePath)/projects/\(projectId)/elements/\(elementId)/folders",
            body: Body(name: name, parent_id: parentId)
        )
    }

    /// Upload a file into an element's repo (optionally a folder within it).
    /// Reuses POST /projects/{id}/files with element_id + folder_id form fields.
    func uploadElementFile(
        projectId: String,
        elementId: String,
        folderId: String? = nil,
        file: (data: Data, filename: String, mimeType: String)
    ) async throws -> MWProjectFile {
        var multipart = MultipartUploadBuilder()
        multipart.addFile(name: "file", filename: file.filename, mimeType: file.mimeType, data: file.data)
        multipart.addField(name: "element_id", value: elementId)
        if let folderId { multipart.addField(name: "folder_id", value: folderId) }
        let (body, contentType) = multipart.finalize()

        guard let url = URL(string: "\(client.baseURL)\(basePath)/projects/\(projectId)/files") else {
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

    func listElementNotes(projectId: String, elementId: String) async throws -> [MWElementNote] {
        try await client.request(method: "GET", path: "\(basePath)/projects/\(projectId)/elements/\(elementId)/notes")
    }

    func addElementNote(projectId: String, elementId: String, kind: String, body: String?, url: String?) async throws -> MWElementNote {
        struct Req: Encodable { let kind: String; let body: String?; let url: String? }
        return try await client.request(
            method: "POST",
            path: "\(basePath)/projects/\(projectId)/elements/\(elementId)/notes",
            body: Req(kind: kind, body: body, url: url)
        )
    }

    func deleteElementNote(projectId: String, elementId: String, noteId: String) async throws {
        _ = try await client.requestData(
            method: "DELETE",
            path: "\(basePath)/projects/\(projectId)/elements/\(elementId)/notes/\(noteId)"
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
        var multipart = MultipartUploadBuilder()
        for file in files {
            multipart.addFile(name: "files", filename: file.filename, mimeType: file.mimeType, data: file.data)
        }
        let (body, contentType) = multipart.finalize()

        guard let url = URL(string: "\(client.baseURL)\(basePath)/projects/\(projectId)/resume/upload") else {
            throw APIError.invalidURL
        }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue(contentType, forHTTPHeaderField: "Content-Type")
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

    // MARK: - Journals (delegate to JournalService)
    //
    // Journal CRUD/entries/collaborators/images live in
    // Services/MatchaWork/JournalService.swift. The facade keeps these
    // delegating shims so the existing 23 callers see no API change.
    // Sub-service owns its own list cache.

    func invalidateJournalLists() {
        JournalService.shared.invalidateLists()
    }

    func listJournals(forceRefresh: Bool = false) async throws -> [MWJournal] {
        try await JournalService.shared.listJournals(forceRefresh: forceRefresh)
    }

    func getJournal(id: String) async throws -> MWJournal {
        try await JournalService.shared.getJournal(id: id)
    }

    func createJournal(
        title: String, description: String? = nil, color: String? = nil, icon: String? = nil,
        kind: String? = nil, folderId: String? = nil
    ) async throws -> MWJournal {
        try await JournalService.shared.createJournal(
            title: title, description: description, color: color, icon: icon,
            kind: kind, folderId: folderId)
    }

    func updateJournal(
        id: String, title: String? = nil, description: String? = nil,
        color: String? = nil, icon: String? = nil, kind: String? = nil
    ) async throws -> MWJournal {
        try await JournalService.shared.updateJournal(id: id, title: title, description: description, color: color, icon: icon, kind: kind)
    }

    func moveJournal(id: String, folderId: String?) async throws -> MWJournal {
        try await JournalService.shared.moveJournal(id: id, folderId: folderId)
    }

    func archiveJournal(id: String) async throws {
        try await JournalService.shared.archiveJournal(id: id)
    }

    // ── Journal folders ─────────────────────────────────────────────────

    func listJournalFolders() async throws -> [MWJournalFolder] {
        try await JournalService.shared.listFolders()
    }

    func createJournalFolder(name: String, parentId: String? = nil) async throws -> MWJournalFolder {
        try await JournalService.shared.createFolder(name: name, parentId: parentId)
    }

    func renameJournalFolder(id: String, name: String) async throws -> MWJournalFolder {
        try await JournalService.shared.renameFolder(id: id, name: name)
    }

    func deleteJournalFolder(id: String) async throws {
        try await JournalService.shared.deleteFolder(id: id)
    }

    func listJournalEntries(
        journalId: String, before: String? = nil, limit: Int = 50
    ) async throws -> [MWJournalEntry] {
        try await JournalService.shared.listJournalEntries(journalId: journalId, before: before, limit: limit)
    }

    func createJournalEntry(
        journalId: String, title: String?, content: String, entryDate: String? = nil
    ) async throws -> MWJournalEntry {
        try await JournalService.shared.createJournalEntry(journalId: journalId, title: title, content: content, entryDate: entryDate)
    }

    func updateJournalEntry(
        entryId: String, journalId: String,
        title: String? = nil, content: String? = nil, entryDate: String? = nil
    ) async throws -> MWJournalEntry {
        try await JournalService.shared.updateJournalEntry(entryId: entryId, journalId: journalId, title: title, content: content, entryDate: entryDate)
    }

    func deleteJournalEntry(entryId: String, journalId: String) async throws {
        try await JournalService.shared.deleteJournalEntry(entryId: entryId, journalId: journalId)
    }

    func listJournalCollaborators(journalId: String) async throws -> [MWProjectCollaborator] {
        try await JournalService.shared.listJournalCollaborators(journalId: journalId)
    }

    func addJournalCollaborators(journalId: String, userIds: [String]) async throws {
        try await JournalService.shared.addJournalCollaborators(journalId: journalId, userIds: userIds)
    }

    func removeJournalCollaborator(journalId: String, userId: String) async throws {
        try await JournalService.shared.removeJournalCollaborator(journalId: journalId, userId: userId)
    }

    func uploadJournalImage(
        journalId: String, data: Data, filename: String, mimeType: String,
    ) async throws -> String {
        try await JournalService.shared.uploadJournalImage(journalId: journalId, data: data, filename: filename, mimeType: mimeType)
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
