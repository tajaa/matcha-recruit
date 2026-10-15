import Foundation
import UniformTypeIdentifiers

/// Espresso Job search (`/matcha-work/job-searches/*`) and the person's saved
/// résumé (`/users/me/resume`), which a search may use when they choose to.
@MainActor
final class JobSearchService {
    static let shared = JobSearchService()
    private let client = APIClient.shared
    private let basePath = "/matcha-work/job-searches"

    func list() async throws -> JobSearchList {
        try await client.request(method: "GET", path: basePath)
    }

    struct CreateBody: Encodable {
        let requestId: UUID
        let title: String
        let ask: String
        let criteria: JobSearchCriteria
        let weights: JobSearchWeights?
        let useResume: Bool
        let consentVersion: String?

        enum CodingKeys: String, CodingKey {
            case title, ask, criteria, weights
            case requestId = "request_id"
            case useResume = "use_resume"
            case consentVersion = "consent_version"
        }
    }

    func create(_ body: CreateBody) async throws -> JobSearchSummary {
        try await client.request(method: "POST", path: basePath, body: body)
    }

    func detail(_ searchId: String) async throws -> JobSearchDetail {
        try await client.request(method: "GET", path: "\(basePath)/\(searchId)")
    }

    func status(_ searchId: String) async throws -> JobSearchStatusView {
        try await client.request(method: "GET", path: "\(basePath)/\(searchId)/status")
    }

    func lead(_ searchId: String, _ leadId: String) async throws -> JobLeadDetail {
        try await client.request(method: "GET", path: "\(basePath)/\(searchId)/leads/\(leadId)")
    }

    func updateLead(_ searchId: String, _ leadId: String, state: String? = nil, notes: String? = nil) async throws -> JobLeadDetail {
        struct Body: Encodable {
            let userState: String?
            let notes: String?
            enum CodingKeys: String, CodingKey {
                case notes
                case userState = "user_state"
            }
            func encode(to encoder: Encoder) throws {
                var c = encoder.container(keyedBy: CodingKeys.self)
                try c.encodeIfPresent(userState, forKey: .userState)
                try c.encodeIfPresent(notes, forKey: .notes)
            }
        }
        return try await client.request(method: "PATCH", path: "\(basePath)/\(searchId)/leads/\(leadId)",
                                        body: Body(userState: state, notes: notes))
    }

    func rerank(_ searchId: String, weights: JobSearchWeights) async throws -> JobSearchDetail {
        try await client.request(method: "PUT", path: "\(basePath)/\(searchId)/weights", body: weights)
    }

    func redraft(_ searchId: String, _ leadId: String) async throws -> JobSearchDetail {
        try await client.request(method: "POST", path: "\(basePath)/\(searchId)/leads/\(leadId)/approach")
    }

    /// Put the job's first message in Gmail drafts; the same draft again
    /// while it is still there.
    func draftEmail(_ searchId: String, _ leadId: String) async throws -> JobEmailDraftResult {
        try await client.request(method: "POST", path: "\(basePath)/\(searchId)/leads/\(leadId)/email-draft")
    }

    func cancel(_ searchId: String) async throws -> JobSearchDetail {
        try await client.request(method: "POST", path: "\(basePath)/\(searchId)/cancel")
    }

    func delete(_ searchId: String) async throws {
        let _: [String: Bool] = try await client.request(method: "DELETE", path: "\(basePath)/\(searchId)")
    }

    // MARK: Résumé

    func resume() async throws -> ProfileResume? {
        try await client.request(method: "GET", path: "/users/me/resume")
    }

    /// The file types the résumé picker offers (the server reads these).
    nonisolated static let resumeTypes: [UTType] = ["pdf", "doc", "docx", "txt"]
        .compactMap { UTType(filenameExtension: $0) }

    /// Upload (or replace) the résumé. The server parses it before answering,
    /// so it gets a longer timeout; an expired login refreshes like any call.
    func uploadResume(data: Data, filename: String) async throws -> ProfileResume {
        var multipart = MultipartUploadBuilder()
        multipart.addFile(name: "file", filename: filename, mimeType: Self.mimeType(for: filename), data: data)
        let (body, contentType) = multipart.finalize()
        return try await client.upload(path: "/users/me/resume", body: body, contentType: contentType)
    }

    nonisolated static func mimeType(for filename: String) -> String {
        UTType(filenameExtension: (filename as NSString).pathExtension.lowercased())?.preferredMIMEType
            ?? "application/octet-stream"
    }
}
