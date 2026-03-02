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

    func removeImage(threadId: String, imageUrl: String) async throws -> [String] {
        let encoded = imageUrl.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? imageUrl
        let path = "\(basePath)/threads/\(threadId)/images?url=\(encoded)"
        struct ImagesResponse: Decodable { let images: [String] }
        let result: ImagesResponse = try await client.request(method: "DELETE", path: path)
        invalidateThread(threadId: threadId)
        return result.images
    }
}
