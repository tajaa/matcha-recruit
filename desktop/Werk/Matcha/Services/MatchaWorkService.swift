import Foundation

class MatchaWorkService {
    static let shared = MatchaWorkService()
    let client = APIClient.shared
    let basePath = "/matcha-work"
    let cacheTTL: TimeInterval = 60
    var cacheScope: String?
    var threadListCache: [String: MWCacheEntry<[MWThread]>] = [:]
    var threadDetailCache: [String: MWCacheEntry<MWThreadDetail>] = [:]
    var versionsCache: [String: MWCacheEntry<[MWDocumentVersion]>] = [:]
    var pdfCache: [String: MWCacheEntry<Data>] = [:]
    var projectListCache: [String: MWCacheEntry<[MWProject]>] = [:]
    var projectDetailCache: [String: MWCacheEntry<MWProject>] = [:]
    // Per-project sub-resource caches (keyed by projectId), so tab- and
    // project-switches paint instantly from cache (stale-while-revalidate)
    // instead of re-fetching 6 endpoints cold every time. Same MWCacheEntry +
    // 60s TTL pattern as projectDetailCache. Populated by the list getters and
    // wholesale by getProjectBundle; invalidated by the matching mutations.
    var projectTasksCache: [String: MWCacheEntry<[MWProjectTask]>] = [:]
    var projectFilesCache: [String: MWCacheEntry<[MWProjectFile]>] = [:]
    var projectFoldersCache: [String: MWCacheEntry<[MWProjectFolder]>] = [:]
    var projectLinksCache: [String: MWCacheEntry<[MWProjectLink]>] = [:]
    var projectCollaboratorsCache: [String: MWCacheEntry<[MWProjectCollaborator]>] = [:]
    var projectElementsCache: [String: MWCacheEntry<[MWProjectElement]>] = [:]
    private init() {}

    func cachedValue<Value>(_ entry: MWCacheEntry<Value>?) -> Value? {
        guard let entry else { return nil }
        guard entry.isValid else { return nil }
        return entry.value
    }

    func makeListCacheKey(status: String?) -> String {
        status ?? "__all__"
    }

    func makePDFCacheKey(threadId: String, version: Int?) -> String {
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
        projectListCache.removeAll()
        projectDetailCache.removeAll()
        projectTasksCache.removeAll()
        projectFilesCache.removeAll()
        projectFoldersCache.removeAll()
        projectLinksCache.removeAll()
        projectCollaboratorsCache.removeAll()
        projectElementsCache.removeAll()
        JournalService.shared.invalidateLists()
    }

    /// Drop cached project lists. Call when project membership in any status
    /// bucket changes (create / delete / status change).
    func invalidateProjectLists() {
        projectListCache.removeAll()
    }

    func invalidateThread(threadId: String) {
        threadDetailCache.removeValue(forKey: threadId)
        versionsCache.removeValue(forKey: threadId)
        pdfCache = pdfCache.filter { !$0.key.hasPrefix("\(threadId):") }
        // Don't wipe threadListCache here — sidebar still has accurate data in
        // its own ViewModel state. Stale cache entries expire on TTL (60s).
        // Listings only need a hard refresh on create/delete/archive/pin/title,
        // which call into the dedicated invalidators below.
    }

    /// Drop the cached thread lists. Call when thread membership in any
    /// status bucket changes (create, delete, archive, pin, title rename).
    func invalidateThreadLists() {
        threadListCache.removeAll()
    }

    // MARK: - Usage Summary

    func fetchUsageSummary(periodDays: Int = 30) async throws -> MWUsageSummary {
        try await client.request(
            method: "GET",
            path: "\(basePath)/usage/summary?period_days=\(periodDays)"
        )
    }

    // MARK: - Presence

    func sendHeartbeat() async throws {
        _ = try await client.requestData(method: "POST", path: "\(basePath)/presence/heartbeat")
    }

    func fetchOnlineUsers() async throws -> [MWOnlineUser] {
        try await client.request(method: "GET", path: "\(basePath)/presence/online")
    }

    // MARK: - Collab Discussion Channel

    func ensureProjectDiscussionChannel(projectId: String) async throws -> String {
        struct Res: Codable { let channel_id: String }
        let res: Res = try await client.request(
            method: "POST",
            path: "\(basePath)/projects/\(projectId)/discussion-channel"
        )
        return res.channel_id
    }

    // MARK: - Notifications

    func fetchNotifications(unreadOnly: Bool = false, limit: Int = 30) async throws -> [MWAppNotification] {
        struct Res: Codable { let notifications: [MWAppNotification] }
        let path = "\(basePath)/notifications?limit=\(limit)&unread_only=\(unreadOnly)"
        let res: Res = try await client.request(method: "GET", path: path)
        return res.notifications
    }

    func fetchNotificationsUnreadCount() async throws -> Int {
        struct Res: Codable { let unread_count: Int }
        let res: Res = try await client.request(method: "GET", path: "\(basePath)/notifications/unread-count")
        return res.unread_count
    }

    /// Per-project unread-notification counts for the tab badges.
    func fetchProjectUnreadCounts() async throws -> [String: Int] {
        struct Res: Codable { let counts: [String: Int] }
        let res: Res = try await client.request(
            method: "GET",
            path: "\(basePath)/notifications/project-unread-counts"
        )
        return res.counts
    }

    /// Clear notifications by the entity the user just opened (ticket, note
    /// section, channel). Drops matching rows from the bell and tab badge.
    func markNotificationsReadBy(
        taskId: String? = nil,
        sectionId: String? = nil,
        channelId: String? = nil,
        projectId: String? = nil
    ) async throws {
        struct Body: Encodable {
            let task_id: String?
            let section_id: String?
            let channel_id: String?
            let project_id: String?
        }
        _ = try await client.requestData(
            method: "POST",
            path: "\(basePath)/notifications/mark-read-by",
            body: Body(task_id: taskId, section_id: sectionId, channel_id: channelId, project_id: projectId)
        )
    }

    func markNotificationsRead(ids: [String]) async throws {
        struct Body: Encodable { let notification_ids: [String] }
        _ = try await client.requestData(
            method: "POST",
            path: "\(basePath)/notifications/mark-read",
            body: Body(notification_ids: ids)
        )
    }

    func markAllNotificationsRead() async throws {
        _ = try await client.requestData(method: "POST", path: "\(basePath)/notifications/mark-all-read")
    }

    // MARK: - Journals (delegate to JournalService)
    //
    // Journal CRUD/entries/collaborators/images live in
    // Services/MatchaWork/JournalService.swift. The facade keeps these
    // delegating shims so the existing 23 callers see no API change.
    // Sub-service owns its own list cache.

    func invalidateJournalLists() {
        JournalService.shared.invalidateLists()
    }

    func listJournals(forceRefresh: Bool = false) async throws -> [MWJournal] {
        try await JournalService.shared.listJournals(forceRefresh: forceRefresh)
    }

    func getJournal(id: String) async throws -> MWJournal {
        try await JournalService.shared.getJournal(id: id)
    }

    func createJournal(
        title: String, description: String? = nil, color: String? = nil, icon: String? = nil,
        kind: String? = nil, folderId: String? = nil
    ) async throws -> MWJournal {
        try await JournalService.shared.createJournal(
            title: title, description: description, color: color, icon: icon,
            kind: kind, folderId: folderId)
    }

    func updateJournal(
        id: String, title: String? = nil, description: String? = nil,
        color: String? = nil, icon: String? = nil, kind: String? = nil
    ) async throws -> MWJournal {
        try await JournalService.shared.updateJournal(id: id, title: title, description: description, color: color, icon: icon, kind: kind)
    }

    func moveJournal(id: String, folderId: String?) async throws -> MWJournal {
        try await JournalService.shared.moveJournal(id: id, folderId: folderId)
    }

    func archiveJournal(id: String) async throws {
        try await JournalService.shared.archiveJournal(id: id)
    }

    // ── Journal folders ─────────────────────────────────────────────────

    func listJournalFolders() async throws -> [MWJournalFolder] {
        try await JournalService.shared.listFolders()
    }

    func createJournalFolder(name: String, parentId: String? = nil, color: String? = nil) async throws -> MWJournalFolder {
        try await JournalService.shared.createFolder(name: name, parentId: parentId, color: color)
    }

    func renameJournalFolder(id: String, name: String) async throws -> MWJournalFolder {
        try await JournalService.shared.renameFolder(id: id, name: name)
    }

    func updateJournalFolder(id: String, name: String? = nil, color: String? = nil) async throws -> MWJournalFolder {
        try await JournalService.shared.updateFolder(id: id, name: name, color: color)
    }

    func deleteJournalFolder(id: String) async throws {
        try await JournalService.shared.deleteFolder(id: id)
    }

    func listJournalEntries(
        journalId: String, before: String? = nil, limit: Int = 50
    ) async throws -> [MWJournalEntry] {
        try await JournalService.shared.listJournalEntries(journalId: journalId, before: before, limit: limit)
    }

    func createJournalEntry(
        journalId: String, title: String?, content: String, entryDate: String? = nil
    ) async throws -> MWJournalEntry {
        try await JournalService.shared.createJournalEntry(journalId: journalId, title: title, content: content, entryDate: entryDate)
    }

    func updateJournalEntry(
        entryId: String, journalId: String,
        title: String? = nil, content: String? = nil, entryDate: String? = nil
    ) async throws -> MWJournalEntry {
        try await JournalService.shared.updateJournalEntry(entryId: entryId, journalId: journalId, title: title, content: content, entryDate: entryDate)
    }

    func deleteJournalEntry(entryId: String, journalId: String) async throws {
        try await JournalService.shared.deleteJournalEntry(entryId: entryId, journalId: journalId)
    }

    func listJournalCollaborators(journalId: String) async throws -> [MWProjectCollaborator] {
        try await JournalService.shared.listJournalCollaborators(journalId: journalId)
    }

    func addJournalCollaborators(journalId: String, userIds: [String]) async throws {
        try await JournalService.shared.addJournalCollaborators(journalId: journalId, userIds: userIds)
    }

    func removeJournalCollaborator(journalId: String, userId: String) async throws {
        try await JournalService.shared.removeJournalCollaborator(journalId: journalId, userId: userId)
    }

    func uploadJournalImage(
        journalId: String, data: Data, filename: String, mimeType: String,
    ) async throws -> String {
        try await JournalService.shared.uploadJournalImage(journalId: journalId, data: data, filename: filename, mimeType: mimeType)
    }
}
