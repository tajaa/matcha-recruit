import Foundation

extension MatchaWorkService {
    // MARK: - Project Files

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
}
