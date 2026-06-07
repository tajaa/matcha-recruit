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
        icon: String? = nil,
        kind: String? = nil,
        folderId: String? = nil
    ) async throws -> MWJournal {
        struct Body: Codable {
            let title: String
            let description: String?
            let color: String?
            let icon: String?
            let kind: String?
            let folderId: String?
            enum CodingKeys: String, CodingKey {
                case title, description, color, icon, kind
                case folderId = "folder_id"
            }
        }
        let journal: MWJournal = try await client.request(
            method: "POST",
            path: "\(basePath)/journals",
            body: Body(title: title, description: description, color: color,
                       icon: icon, kind: kind, folderId: folderId),
        )
        invalidateLists()
        return journal
    }

    func updateJournal(
        id: String,
        title: String? = nil,
        description: String? = nil,
        color: String? = nil,
        icon: String? = nil,
        kind: String? = nil
    ) async throws -> MWJournal {
        struct Body: Codable {
            let title: String?
            let description: String?
            let color: String?
            let icon: String?
            let kind: String?
        }
        let journal: MWJournal = try await client.request(
            method: "PATCH",
            path: "\(basePath)/journals/\(id)",
            body: Body(title: title, description: description, color: color, icon: icon, kind: kind),
        )
        invalidateLists()
        return journal
    }

    /// Move a journal into a folder, or to the hub root (`folderId == nil`,
    /// which sends an explicit JSON null so the backend un-files it).
    func moveJournal(id: String, folderId: String?) async throws -> MWJournal {
        struct Body: Encodable {
            let folderId: String?
            enum CodingKeys: String, CodingKey { case folderId = "folder_id" }
            func encode(to encoder: Encoder) throws {
                var c = encoder.container(keyedBy: CodingKeys.self)
                // Always encode the key (even when nil) so the move-to-root
                // intent reaches the server as `folder_id: null`.
                try c.encode(folderId, forKey: .folderId)
            }
        }
        let journal: MWJournal = try await client.request(
            method: "PATCH",
            path: "\(basePath)/journals/\(id)",
            body: Body(folderId: folderId),
        )
        invalidateLists()
        return journal
    }

    // ── Folders ─────────────────────────────────────────────────────────

    func listFolders() async throws -> [MWJournalFolder] {
        try await client.request(method: "GET", path: "\(basePath)/journal-folders")
    }

    func createFolder(name: String, parentId: String? = nil, color: String? = nil) async throws -> MWJournalFolder {
        struct Body: Codable {
            let name: String
            let parentId: String?
            let color: String?
            enum CodingKeys: String, CodingKey {
                case name, color
                case parentId = "parent_id"
            }
        }
        return try await client.request(
            method: "POST",
            path: "\(basePath)/journal-folders",
            body: Body(name: name, parentId: parentId, color: color),
        )
    }

    func renameFolder(id: String, name: String) async throws -> MWJournalFolder {
        try await updateFolder(id: id, name: name)
    }

    /// Patch a folder's name and/or color. A nil field is sent as JSON null,
    /// which the backend skips (only non-nil patch keys are applied).
    func updateFolder(id: String, name: String? = nil, color: String? = nil) async throws -> MWJournalFolder {
        struct Body: Codable { let name: String?; let color: String? }
        return try await client.request(
            method: "PATCH",
            path: "\(basePath)/journal-folders/\(id)",
            body: Body(name: name, color: color),
        )
    }

    func deleteFolder(id: String) async throws {
        _ = try await client.requestData(method: "DELETE", path: "\(basePath)/journal-folders/\(id)")
    }

    func archiveJournal(id: String) async throws {
        _ = try await client.requestData(method: "DELETE", path: "\(basePath)/journals/\(id)")
        invalidateLists()
    }

    func listArchivedJournals() async throws -> [MWJournal] {
        try await client.request(method: "GET", path: "\(basePath)/journals?status=archived")
    }

    func unarchiveJournal(id: String) async throws {
        _ = try await client.requestData(method: "POST", path: "\(basePath)/journals/\(id)/unarchive")
        invalidateLists()
    }

    func deleteJournal(id: String) async throws {
        _ = try await client.requestData(method: "DELETE", path: "\(basePath)/journals/\(id)/permanent")
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
