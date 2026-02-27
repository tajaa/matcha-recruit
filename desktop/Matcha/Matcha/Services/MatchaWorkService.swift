import Foundation

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
}
