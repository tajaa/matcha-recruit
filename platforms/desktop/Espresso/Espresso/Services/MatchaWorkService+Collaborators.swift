import Foundation

extension MatchaWorkService {
    // MARK: - Collaborators

    func cachedCollaborators(_ projectId: String) -> [MWProjectCollaborator]? { cachedValue(projectCollaboratorsCache[projectId]) }
    func invalidateCollaborators(projectId: String) { projectCollaboratorsCache.removeValue(forKey: projectId) }

    func listCollaborators(projectId: String, forceRefresh: Bool = false) async throws -> [MWProjectCollaborator] {
        if !forceRefresh, let cached = cachedValue(projectCollaboratorsCache[projectId]) { return cached }
        let result: [MWProjectCollaborator] = try await client.request(method: "GET", path: "\(basePath)/projects/\(projectId)/collaborators")
        projectCollaboratorsCache[projectId] = MWCacheEntry(value: result, expiresAt: Date().addingTimeInterval(cacheTTL))
        return result
    }

    func addCollaborator(projectId: String, userId: String) async throws {
        struct Body: Codable { let userId: String; let role: String; enum CodingKeys: String, CodingKey { case userId = "user_id"; case role } }
        _ = try await client.requestData(method: "POST", path: "\(basePath)/projects/\(projectId)/collaborators", body: Body(userId: userId, role: "collaborator"))
        invalidateCollaborators(projectId: projectId)
    }

    func removeCollaborator(projectId: String, userId: String) async throws {
        _ = try await client.requestData(method: "DELETE", path: "\(basePath)/projects/\(projectId)/collaborators/\(userId)")
        invalidateCollaborators(projectId: projectId)
    }

    func searchAdminUsers(query: String) async throws -> [MWAdminSearchUser] {
        let encoded = query.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? query
        return try await client.request(method: "GET", path: "\(basePath)/admin-users/search?q=\(encoded)")
    }

    func searchInvitableUsers(query: String) async throws -> [MWAdminSearchUser] {
        // urlQueryAllowed leaves "+", "&", "=" unencoded which breaks emails
        // like "user+tag@gmail.com" — Starlette decodes "+" as a space.
        var allowed = CharacterSet.urlQueryAllowed
        allowed.remove(charactersIn: "+&=#?")
        let encoded = query.addingPercentEncoding(withAllowedCharacters: allowed) ?? query
        return try await client.request(method: "GET", path: "/channels/invitable-users?q=\(encoded)")
    }
}
