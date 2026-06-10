import Foundation

extension MatchaWorkService {
    // MARK: - Productivity (personal kanban)

    func listProductivityBoards() async throws -> [ProductivityBoard] {
        try await client.request(method: "GET", path: "\(basePath)/productivity/boards")
    }

    func createProductivityBoard(title: String) async throws -> ProductivityBoard {
        struct Body: Encodable { let title: String }
        return try await client.request(
            method: "POST", path: "\(basePath)/productivity/boards", body: Body(title: title))
    }

    func renameProductivityBoard(id: String, title: String) async throws -> ProductivityBoard {
        struct Body: Encodable { let title: String }
        return try await client.request(
            method: "PATCH", path: "\(basePath)/productivity/boards/\(id)", body: Body(title: title))
    }

    func deleteProductivityBoard(id: String) async throws {
        _ = try await client.requestData(method: "DELETE", path: "\(basePath)/productivity/boards/\(id)")
    }

    func listProductivityCards(boardId: String) async throws -> [ProductivityCard] {
        try await client.request(method: "GET", path: "\(basePath)/productivity/boards/\(boardId)/cards")
    }

    func createProductivityCard(boardId: String, title: String, column: String = "todo") async throws -> ProductivityCard {
        struct Body: Encodable { let title: String; let board_column: String }
        return try await client.request(
            method: "POST", path: "\(basePath)/productivity/boards/\(boardId)/cards",
            body: Body(title: title, board_column: column))
    }

    /// Move a card to a different column. Server appends it to the bottom of the
    /// target column and syncs completed_at for `done`.
    func moveProductivityCard(id: String, column: String) async throws -> ProductivityCard {
        struct Body: Encodable { let board_column: String }
        return try await client.request(
            method: "PATCH", path: "\(basePath)/productivity/cards/\(id)", body: Body(board_column: column))
    }

    func renameProductivityCard(id: String, title: String) async throws -> ProductivityCard {
        struct Body: Encodable { let title: String }
        return try await client.request(
            method: "PATCH", path: "\(basePath)/productivity/cards/\(id)", body: Body(title: title))
    }

    func deleteProductivityCard(id: String) async throws {
        _ = try await client.requestData(method: "DELETE", path: "\(basePath)/productivity/cards/\(id)")
    }

    /// Journal selection → to-do: drops a card on the user's default board.
    @discardableResult
    func quickTodo(title: String, sourceJournalId: String?, sourceExcerpt: String?) async throws -> ProductivityCard {
        struct Body: Encodable {
            let title: String
            let source_journal_id: String?
            let source_excerpt: String?
        }
        return try await client.request(
            method: "POST", path: "\(basePath)/productivity/quick-todo",
            body: Body(title: title, source_journal_id: sourceJournalId, source_excerpt: sourceExcerpt))
    }
}
