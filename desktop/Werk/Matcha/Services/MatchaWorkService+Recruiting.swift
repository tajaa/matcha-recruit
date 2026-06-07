import Foundation

extension MatchaWorkService {
    // MARK: - Recruiting

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
