import Foundation

extension MatchaWorkService {
    // MARK: - Threads

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

    func removeImage(threadId: String, imageUrl: String) async throws -> [String] {
        let encoded = imageUrl.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? imageUrl
        let path = "\(basePath)/threads/\(threadId)/images?url=\(encoded)"
        struct ImagesResponse: Decodable { let images: [String] }
        let result: ImagesResponse = try await client.request(method: "DELETE", path: path)
        invalidateThread(threadId: threadId)
        return result.images
    }
}
