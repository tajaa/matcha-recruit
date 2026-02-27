import Foundation

private extension Data {
    mutating func append(_ string: String) {
        if let d = string.data(using: .utf8) { append(d) }
    }
}

class MatchaWorkService {
    static let shared = MatchaWorkService()
    private let client = APIClient.shared
    private let basePath = "/matcha-work"
    private init() {}

    func listThreads(status: String? = nil) async throws -> [MWThread] {
        var path = "\(basePath)/threads?limit=50"
        if let status = status { path += "&status=\(status)" }
        return try await client.request(method: "GET", path: path)
    }

    func getThread(id: String) async throws -> MWThreadDetail {
        return try await client.request(method: "GET", path: "\(basePath)/threads/\(id)")
    }

    func createThread(title: String?, taskType: String, initialMessage: String?) async throws -> MWThread {
        let body = MWCreateThreadRequest(title: title, taskType: taskType, initialMessage: initialMessage)
        let response: MWCreateThreadResponse = try await client.request(method: "POST", path: "\(basePath)/threads", body: body)
        return response.toThread()
    }

    func deleteThread(id: String) async throws {
        _ = try await client.requestData(method: "DELETE", path: "\(basePath)/threads/\(id)")
    }

    func setPinned(id: String, pinned: Bool) async throws {
        let body = MWPinRequest(pinned: pinned)
        _ = try await client.requestData(method: "POST", path: "\(basePath)/threads/\(id)/pin", body: body)
    }

    func getVersions(threadId: String) async throws -> [MWDocumentVersion] {
        return try await client.request(method: "GET", path: "\(basePath)/threads/\(threadId)/versions")
    }

    func revertThread(id: String, version: Int) async throws -> MWThread {
        let body = MWRevertRequest(version: version)
        return try await client.request(method: "POST", path: "\(basePath)/threads/\(id)/revert", body: body)
    }

    func finalizeThread(id: String) async throws -> MWThread {
        return try await client.request(method: "POST", path: "\(basePath)/threads/\(id)/finalize")
    }

    func getPDFData(threadId: String, version: Int? = nil) async throws -> Data {
        var path = "\(basePath)/threads/\(threadId)/pdf"
        if let v = version { path += "?version=\(v)" }
        // Step 1: get the signed URL from the backend
        let response: PDFResponse = try await client.request(method: "GET", path: path)
        // Step 2: download the actual PDF bytes from the CDN URL
        guard let url = URL(string: response.pdfUrl) else { throw APIError.invalidURL }
        let (data, _) = try await URLSession.shared.data(from: url)
        return data
    }

    private struct PDFResponse: Decodable {
        let pdfUrl: String
        enum CodingKeys: String, CodingKey { case pdfUrl = "pdf_url" }
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
        return try JSONDecoder().decode(ImagesResponse.self, from: data).images
    }

    func removeImage(threadId: String, imageUrl: String) async throws -> [String] {
        let encoded = imageUrl.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? imageUrl
        let path = "\(basePath)/threads/\(threadId)/images?url=\(encoded)"
        struct ImagesResponse: Decodable { let images: [String] }
        let result: ImagesResponse = try await client.request(method: "DELETE", path: path)
        return result.images
    }
}
