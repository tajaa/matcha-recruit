import Foundation

// MARK: - Journals

struct MWJournal: Codable, Identifiable, Hashable {
    let id: String
    let title: String
    let description: String?
    let color: String?
    let icon: String?
    let status: String
    let createdBy: String
    let createdAt: String?
    let updatedAt: String?
    let entryCount: Int?
    let collaboratorCount: Int?
    let collaboratorRole: String?

    enum CodingKeys: String, CodingKey {
        case id, title, description, color, icon, status
        case createdBy = "created_by"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
        case entryCount = "entry_count"
        case collaboratorCount = "collaborator_count"
        case collaboratorRole = "collaborator_role"
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
