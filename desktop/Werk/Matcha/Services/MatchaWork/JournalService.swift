import Foundation

/// Journal CRUD + entries + collaborators + image upload.
/// Owned by `MatchaWorkService` as an internal singleton; the facade
/// delegates each public journal method here. Sub-service owns its own
/// list cache; the facade's `clearCaches()` calls into `invalidateLists()`.
final class JournalService {
    static let shared = JournalService()
    private let client = APIClient.shared
    private let basePath = "/matcha-work"
    private let cacheTTL: TimeInterval = 60
    private var listCache: [String: MWCacheEntry<[MWJournal]>] = [:]

    private init() {}

    func invalidateLists() {
        listCache.removeAll()
    }

    func listJournals(forceRefresh: Bool = false) async throws -> [MWJournal] {
        let key = "all"
        if !forceRefresh, let entry = listCache[key], entry.isValid {
            return entry.value
        }
        let journals: [MWJournal] = try await client.request(method: "GET", path: "\(basePath)/journals")
        listCache[key] = MWCacheEntry(value: journals, expiresAt: Date().addingTimeInterval(cacheTTL))
        return journals
    }

    func getJournal(id: String) async throws -> MWJournal {
        try await client.request(method: "GET", path: "\(basePath)/journals/\(id)")
    }

    func createJournal(
        title: String,
        description: String? = nil,
        color: String? = nil,
        icon: String? = nil
    ) async throws -> MWJournal {
        struct Body: Codable {
            let title: String
            let description: String?
            let color: String?
            let icon: String?
        }
        let journal: MWJournal = try await client.request(
            method: "POST",
            path: "\(basePath)/journals",
            body: Body(title: title, description: description, color: color, icon: icon),
        )
        invalidateLists()
        return journal
    }

    func updateJournal(
        id: String,
        title: String? = nil,
        description: String? = nil,
        color: String? = nil,
        icon: String? = nil
    ) async throws -> MWJournal {
        struct Body: Codable {
            let title: String?
            let description: String?
            let color: String?
            let icon: String?
        }
        let journal: MWJournal = try await client.request(
            method: "PATCH",
            path: "\(basePath)/journals/\(id)",
            body: Body(title: title, description: description, color: color, icon: icon),
        )
        invalidateLists()
        return journal
    }

    func archiveJournal(id: String) async throws {
        _ = try await client.requestData(method: "DELETE", path: "\(basePath)/journals/\(id)")
        invalidateLists()
    }

    func listJournalEntries(
        journalId: String, before: String? = nil, limit: Int = 50
    ) async throws -> [MWJournalEntry] {
        var path = "\(basePath)/journals/\(journalId)/entries?limit=\(limit)"
        if let before { path += "&before=\(before)" }
        return try await client.request(method: "GET", path: path)
    }

    func createJournalEntry(
        journalId: String, title: String?, content: String, entryDate: String? = nil
    ) async throws -> MWJournalEntry {
        struct Body: Codable {
            let title: String?
            let content: String
            let entryDate: String?
            enum CodingKeys: String, CodingKey {
                case title, content
                case entryDate = "entry_date"
            }
        }
        let entry: MWJournalEntry = try await client.request(
            method: "POST",
            path: "\(basePath)/journals/\(journalId)/entries",
            body: Body(title: title, content: content, entryDate: entryDate),
        )
        invalidateLists()
        return entry
    }

    func updateJournalEntry(
        entryId: String, journalId: String,
        title: String? = nil, content: String? = nil, entryDate: String? = nil
    ) async throws -> MWJournalEntry {
        struct Body: Codable {
            let title: String?
            let content: String?
            let entryDate: String?
            enum CodingKeys: String, CodingKey {
                case title, content
                case entryDate = "entry_date"
            }
        }
        return try await client.request(
            method: "PATCH",
            path: "\(basePath)/journals/\(journalId)/entries/\(entryId)",
            body: Body(title: title, content: content, entryDate: entryDate),
        )
    }

    func deleteJournalEntry(entryId: String, journalId: String) async throws {
        _ = try await client.requestData(
            method: "DELETE",
            path: "\(basePath)/journals/\(journalId)/entries/\(entryId)",
        )
    }

    func listJournalCollaborators(journalId: String) async throws -> [MWProjectCollaborator] {
        try await client.request(method: "GET", path: "\(basePath)/journals/\(journalId)/collaborators")
    }

    func addJournalCollaborators(journalId: String, userIds: [String]) async throws {
        struct Body: Codable { let userIds: [String]; enum CodingKeys: String, CodingKey { case userIds = "user_ids" } }
        _ = try await client.requestData(
            method: "POST",
            path: "\(basePath)/journals/\(journalId)/collaborators",
            body: Body(userIds: userIds),
        )
    }

    func removeJournalCollaborator(journalId: String, userId: String) async throws {
        _ = try await client.requestData(
            method: "DELETE",
            path: "\(basePath)/journals/\(journalId)/collaborators/\(userId)",
        )
    }

    /// Upload a single image for inline embedding in a journal entry.
    /// Returns the public URL the markdown `![](url)` can point at.
    func uploadJournalImage(
        journalId: String, data: Data, filename: String, mimeType: String,
    ) async throws -> String {
        var multipart = MultipartUploadBuilder()
        multipart.addFile(name: "file", filename: filename, mimeType: mimeType, data: data)
        let (body, contentType) = multipart.finalize()

        guard let url = URL(string: "\(client.baseURL)\(basePath)/journals/\(journalId)/images") else {
            throw APIError.invalidURL
        }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue(contentType, forHTTPHeaderField: "Content-Type")
        if let token = client.accessToken {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        request.httpBody = body

        let (respData, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
            let msg = String(data: respData, encoding: .utf8) ?? "Upload failed"
            throw APIError.httpError((response as? HTTPURLResponse)?.statusCode ?? 0, msg)
        }
        struct ImageResponse: Decodable { let url: String }
        return try JSONDecoder().decode(ImageResponse.self, from: respData).url
    }
}
