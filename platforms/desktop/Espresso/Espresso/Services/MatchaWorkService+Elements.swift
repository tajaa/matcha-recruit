import Foundation

extension MatchaWorkService {
    // MARK: - Elements

    func cachedProjectElements(_ projectId: String) -> [MWProjectElement]? { cachedValue(projectElementsCache[projectId]) }
    func invalidateProjectElements(projectId: String) { projectElementsCache.removeValue(forKey: projectId) }

    func listProjectElements(projectId: String, forceRefresh: Bool = false) async throws -> [MWProjectElement] {
        if !forceRefresh, let cached = cachedValue(projectElementsCache[projectId]) { return cached }
        let result: [MWProjectElement] = try await client.request(method: "GET", path: "\(basePath)/projects/\(projectId)/elements")
        projectElementsCache[projectId] = MWCacheEntry(value: result, expiresAt: Date().addingTimeInterval(cacheTTL))
        return result
    }

    func createProjectElement(
        projectId: String,
        name: String,
        kind: String? = nil,
        description: String? = nil,
        assignedTo: String? = nil
    ) async throws -> MWProjectElement {
        struct Body: Encodable {
            let name: String
            let kind: String?
            let description: String?
            let assigned_to: String?
        }
        defer { invalidateProjectElements(projectId: projectId) }
        return try await client.request(
            method: "POST",
            path: "\(basePath)/projects/\(projectId)/elements",
            body: Body(name: name, kind: kind, description: description, assigned_to: assignedTo)
        )
    }

    func updateProjectElement(
        projectId: String,
        elementId: String,
        name: String? = nil,
        kind: String? = nil,
        description: String? = nil,
        assignedTo: String? = nil,
        repoPaths: [String]? = nil,
        repoBranch: String? = nil
    ) async throws -> MWProjectElement {
        struct Body: Encodable {
            let name: String?
            let kind: String?
            let description: String?
            let assigned_to: String?
            let repo_paths: [String]?
            let repo_branch: String?
        }
        defer { invalidateProjectElements(projectId: projectId) }
        // nil optionals are omitted by JSONEncoder, so only the fields actually
        // passed in get patched. To clear the branch pin pass "" (backend maps
        // falsy → NULL).
        return try await client.request(
            method: "PATCH",
            path: "\(basePath)/projects/\(projectId)/elements/\(elementId)",
            body: Body(name: name, kind: kind, description: description,
                       assigned_to: assignedTo, repo_paths: repoPaths, repo_branch: repoBranch)
        )
    }

    func deleteProjectElement(projectId: String, elementId: String) async throws {
        _ = try await client.requestData(
            method: "DELETE",
            path: "\(basePath)/projects/\(projectId)/elements/\(elementId)"
        )
        invalidateProjectElements(projectId: projectId)
    }

    // MARK: - Commit-driven subtask suggestions

    func listCommitSuggestions(projectId: String, taskId: String? = nil) async throws -> [MWCommitSuggestion] {
        var path = "\(basePath)/projects/\(projectId)/commit-suggestions"
        if let taskId { path += "?task_id=\(taskId)" }
        return try await client.request(method: "GET", path: path)
    }

    func acceptCommitSuggestion(projectId: String, suggestionId: String) async throws {
        _ = try await client.requestData(
            method: "POST",
            path: "\(basePath)/projects/\(projectId)/commit-suggestions/\(suggestionId)/accept"
        )
    }

    func dismissCommitSuggestion(projectId: String, suggestionId: String) async throws {
        _ = try await client.requestData(
            method: "POST",
            path: "\(basePath)/projects/\(projectId)/commit-suggestions/\(suggestionId)/dismiss"
        )
    }

    // MARK: - GitHub connection

    func getGitHubConnection(projectId: String) async throws -> GitHubConnection {
        try await client.request(method: "GET", path: "\(basePath)/projects/\(projectId)/github/connection")
    }

    /// Connect/change the project's GitHub repo (validated server-side). Empty
    /// repo disconnects.
    func setGitHubConnection(projectId: String, repo: String, branch: String?) async throws -> GitHubConnection {
        struct Body: Encodable { let repo: String; let branch: String? }
        return try await client.request(
            method: "PUT",
            path: "\(basePath)/projects/\(projectId)/github/connection",
            body: Body(repo: repo, branch: branch)
        )
    }

    /// Pull every bound element's code from GitHub (read-only token, server-side)
    /// into its snapshot. No local clone / bookmark needed.
    func syncFromGitHub(projectId: String) async throws -> GitHubSyncResult {
        struct EmptyBody: Encodable {}
        return try await client.request(
            method: "POST",
            path: "\(basePath)/projects/\(projectId)/github/sync",
            body: EmptyBody()
        )
    }

    /// Pull commits from GitHub (no local git) → commit→subtask matcher →
    /// suggestions on tickets. `force` re-scans recent commits (manual button);
    /// otherwise only NEW commits since the last scan (watermark). Returns
    /// (commits evaluated, pending list).
    func scanCommitsFromGitHub(projectId: String, force: Bool = false) async throws -> (scanned: Int, suggestions: [MWCommitSuggestion]) {
        struct Body: Encodable { let force: Bool }
        struct Resp: Decodable { let scanned: Int; let suggestions: [MWCommitSuggestion] }
        let r: Resp = try await client.request(
            method: "POST",
            path: "\(basePath)/projects/\(projectId)/github/scan-commits",
            body: Body(force: force)
        )
        return (r.scanned, r.suggestions)
    }

    /// Register a GitHub push webhook on the connected repo so a merge triggers a
    /// scan automatically (no polling). Returns true if installed/already present.
    @discardableResult
    func installGitHubWebhook(projectId: String) async throws -> Bool {
        struct EmptyBody: Encodable {}
        struct Resp: Decodable { let installed: Bool? }
        let r: Resp = try await client.request(
            method: "POST",
            path: "\(basePath)/projects/\(projectId)/github/webhook/install",
            body: EmptyBody()
        )
        return r.installed ?? false
    }

    // MARK: - Prop draft tickets

    func listTicketDrafts(projectId: String, status: String? = nil) async throws -> [MWTicketDraft] {
        var path = "\(basePath)/projects/\(projectId)/ticket-drafts"
        if let status { path += "?status=\(status)" }
        return try await client.request(method: "GET", path: path)
    }

    func createTicketDraft(projectId: String, kind: String, title: String? = nil, elementId: String? = nil) async throws -> MWTicketDraft {
        struct Body: Encodable { let kind: String; let title: String?; let element_id: String? }
        return try await client.request(
            method: "POST",
            path: "\(basePath)/projects/\(projectId)/ticket-drafts",
            body: Body(kind: kind, title: title, element_id: elementId)
        )
    }

    func getTicketDraft(projectId: String, draftId: String) async throws -> MWTicketDraft {
        try await client.request(method: "GET", path: "\(basePath)/projects/\(projectId)/ticket-drafts/\(draftId)")
    }

    struct TicketDraftPatch: Encodable {
        var kind: String?
        var title: String?
        var description: String?
        var priority: String?
        var element_id: String?
        var status: String?
        var draft_subtasks: [String]?
    }

    func updateTicketDraft(projectId: String, draftId: String, patch: TicketDraftPatch) async throws -> MWTicketDraft {
        try await client.request(
            method: "PATCH",
            path: "\(basePath)/projects/\(projectId)/ticket-drafts/\(draftId)",
            body: patch
        )
    }

    func deleteTicketDraft(projectId: String, draftId: String) async throws {
        _ = try await client.requestData(
            method: "DELETE",
            path: "\(basePath)/projects/\(projectId)/ticket-drafts/\(draftId)"
        )
    }

    func listPropMessages(projectId: String, draftId: String) async throws -> [MWPropMessage] {
        try await client.request(method: "GET", path: "\(basePath)/projects/\(projectId)/ticket-drafts/\(draftId)/messages")
    }

    func postPropMessage(projectId: String, draftId: String, content: String) async throws -> MWPropChatTurn {
        struct Body: Encodable { let content: String }
        return try await client.request(
            method: "POST",
            path: "\(basePath)/projects/\(projectId)/ticket-drafts/\(draftId)/messages",
            body: Body(content: content)
        )
    }

    func generateDraftFields(projectId: String, draftId: String) async throws -> MWTicketDraft {
        try await client.request(
            method: "POST",
            path: "\(basePath)/projects/\(projectId)/ticket-drafts/\(draftId)/generate"
        )
    }

    struct PromoteOverrides: Encodable {
        var title: String?
        var description: String?
        var priority: String?
        var category: String?
        var board_column: String?
        var element_id: String?
        var assigned_to: String?
        var subtasks: [String]?
    }

    func promoteDraft(projectId: String, draftId: String, overrides: PromoteOverrides) async throws -> MWProjectTask {
        try await client.request(
            method: "POST",
            path: "\(basePath)/projects/\(projectId)/ticket-drafts/\(draftId)/promote",
            body: overrides
        )
    }
}
