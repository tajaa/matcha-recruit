import Foundation

// MARK: - Journals

struct MWJournal: Codable, Identifiable, Hashable {
    let id: String
    let title: String
    let description: String?
    let color: String?
    let icon: String?
    let status: String
    let kind: String?           // note|blog|todo|novel|screenplay|journal
    let folderId: String?       // hub-folder placement (nil = root)
    let createdBy: String
    let ownerName: String?      // display name of created_by — for the "Shared by" badge
    let createdAt: String?
    let updatedAt: String?
    let entryCount: Int?
    let collaboratorCount: Int?
    let collaboratorRole: String?   // non-nil ⟹ this journal is SHARED WITH me (I'm a collaborator, not the owner)
    let preview: String?        // one-line body snippet for the Notes-style list

    /// True when the journal was shared with me by someone else. Owners never
    /// have a collaborator row, so a present collaborator role means it's not mine.
    var isSharedWithMe: Bool { collaboratorRole != nil }

    enum CodingKeys: String, CodingKey {
        case id, title, description, color, icon, status, kind, preview
        case folderId = "folder_id"
        case createdBy = "created_by"
        case ownerName = "owner_name"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
        case entryCount = "entry_count"
        case collaboratorCount = "collaborator_count"
        case collaboratorRole = "collaborator_role"
    }
}

/// A folder in the Journals hub. Company-scoped adjacency-list tree
/// (`parentId == nil` → root). The client builds the hierarchy from the flat
/// list returned by `/matcha-work/journal-folders`.
struct MWJournalFolder: Codable, Identifiable, Hashable {
    let id: String
    let name: String
    let parentId: String?
    let createdBy: String?
    let createdAt: String?
    let color: String?

    enum CodingKeys: String, CodingKey {
        case id, name, color
        case parentId = "parent_id"
        case createdBy = "created_by"
        case createdAt = "created_at"
    }
}

struct MWJournalEntry: Codable, Identifiable, Hashable {
    let id: String
    let journalId: String
    let authorId: String
    let title: String?
    let content: String
    let entryDate: String        // YYYY-MM-DD
    let createdAt: String?
    let updatedAt: String?

    enum CodingKeys: String, CodingKey {
        case id, title, content
        case journalId = "journal_id"
        case authorId = "author_id"
        case entryDate = "entry_date"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }
}
