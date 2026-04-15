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
    }

    func invalidateThread(threadId: String) {
        threadDetailCache.removeValue(forKey: threadId)
        versionsCache.removeValue(forKey: threadId)
        pdfCache = pdfCache.filter { !$0.key.hasPrefix("\(threadId):") }
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
        threadListCache.removeAll()
        return response.toThread()
    }

    func deleteThread(id: String) async throws {
        _ = try await client.requestData(method: "DELETE", path: "\(basePath)/threads/\(id)")
        invalidateThread(threadId: id)
    }

    func setPinned(id: String, pinned: Bool) async throws -> MWThread {
        let body = MWPinRequest(pinned: pinned)
        let thread: MWThread = try await client.request(
            method: "POST",
            path: "\(basePath)/threads/\(id)/pin",
            body: body
        )
        invalidateThread(threadId: id)
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
        return thread
    }

    func archiveThread(id: String) async throws {
        _ = try await client.requestData(method: "DELETE", path: "\(basePath)/threads/\(id)")
        invalidateThread(threadId: id)
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

    func listProjects(status: String? = nil) async throws -> [MWProject] {
        var path = "\(basePath)/projects"
        if let s = status { path += "?status=\(s)" }
        return try await client.request(method: "GET", path: path)
    }

    func createProject(title: String, projectType: String = "general") async throws -> MWProject {
        struct Body: Codable { let title: String; let projectType: String
            enum CodingKeys: String, CodingKey { case title; case projectType = "project_type" }
        }
        return try await client.request(method: "POST", path: "\(basePath)/projects", body: Body(title: title, projectType: projectType))
    }

    func getProjectDetail(id: String) async throws -> MWProject {
        try await client.request(method: "GET", path: "\(basePath)/projects/\(id)")
    }

    func updateProjectMeta(id: String, title: String? = nil, isPinned: Bool? = nil, status: String? = nil) async throws -> MWProject {
        struct Body: Codable { let title: String?; let isPinned: Bool?; let status: String?
            enum CodingKeys: String, CodingKey { case title; case isPinned = "is_pinned"; case status }
        }
        return try await client.request(method: "PATCH", path: "\(basePath)/projects/\(id)", body: Body(title: title, isPinned: isPinned, status: status))
    }

    func archiveProject(id: String) async throws {
        _ = try await client.requestData(method: "DELETE", path: "\(basePath)/projects/\(id)")
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

    func createProjectChat(projectId: String, title: String? = nil) async throws -> MWThread {
        struct Body: Codable { let title: String? }
        return try await client.request(method: "POST", path: "\(basePath)/projects/\(projectId)/chats", body: Body(title: title))
    }

    func exportProject(projectId: String, format: String) async throws -> Data {
        try await client.requestData(method: "GET", path: "\(basePath)/projects/\(projectId)/export/\(format)")
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
}
