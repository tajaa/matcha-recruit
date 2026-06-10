import SwiftUI

/// The Productivity hub: personal kanban boards. Left rail lists the user's
/// boards; the right pane is a simple 3-column board (To Do / In Progress /
/// Done) with drag-to-move. Cards can originate from a journal text selection
/// (they carry a back-link to the source journal).
struct ProductivityWorkspace: View {
    @Environment(AppState.self) private var appState
    @State private var vm = ProductivityViewModel()
    @State private var railCollapsed = false

    var body: some View {
        HSplitView {
            if railCollapsed {
                MWHubRailStrip { railCollapsed = false }
            } else {
                boardRail.frame(minWidth: 190, idealWidth: 220, maxWidth: 280)
            }
            boardPane.frame(minWidth: 460, maxWidth: .infinity, maxHeight: .infinity)
        }
        .background(ThemeRadialBackground())
        .task { await vm.loadBoards() }
    }

    // ── Board rail ──────────────────────────────────────────────────────
    private var boardRail: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Text("Boards")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundColor(appState.themeTextSecondary)
                Spacer()
                Button { railCollapsed = true } label: {
                    Image(systemName: "sidebar.left").font(.system(size: 12))
                }
                .buttonStyle(.plain).foregroundColor(appState.themeTextSecondary)
                .help("Hide sidebar")
                Button { Task { await vm.createBoard() } } label: {
                    Image(systemName: "plus").font(.system(size: 12))
                }
                .buttonStyle(.plain).foregroundColor(appState.themeTextSecondary)
                .help("New board")
            }
            .padding(.horizontal, 14).padding(.top, 14).padding(.bottom, 8)

            ScrollView {
                LazyVStack(alignment: .leading, spacing: 1) {
                    ForEach(vm.boards) { board in boardRow(board) }
                }
                .padding(.horizontal, 8).padding(.bottom, 12)
            }
        }
        .frame(maxHeight: .infinity, alignment: .top)
        .background(appState.themeSidebar.opacity(0.5))
    }

    private func boardRow(_ board: ProductivityBoard) -> some View {
        let selected = vm.selectedBoardId == board.id
        return Button { Task { await vm.select(board.id) } } label: {
            HStack(spacing: 7) {
                Image(systemName: "checklist")
                    .font(.system(size: 11))
                    .foregroundColor(selected ? appState.themeAccent : appState.themeTextSecondary)
                    .frame(width: 15)
                Text(board.title)
                    .font(.system(size: 12, weight: selected ? .semibold : .regular))
                    .foregroundColor(appState.themeText.opacity(0.92))
                    .lineLimit(1)
                Spacer(minLength: 0)
                if board.cardCount > 0 {
                    Text("\(board.cardCount)")
                        .font(.system(size: 10))
                        .foregroundColor(appState.themeTextSecondary)
                }
            }
            .padding(.horizontal, 8).padding(.vertical, 5)
            .background(RoundedRectangle(cornerRadius: 6).fill(selected ? appState.themeAccent.opacity(0.14) : .clear))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .contextMenu {
            Button("Rename…") { vm.beginRename(board) }
            if !board.isDefault {
                Button("Delete board", role: .destructive) { Task { await vm.deleteBoard(board) } }
            }
        }
    }

    // ── Board pane (3 columns) ──────────────────────────────────────────
    @ViewBuilder
    private var boardPane: some View {
        if vm.boards.isEmpty && !vm.isLoading {
            emptyState(icon: "checklist", title: "No boards yet", sub: "Create a board to start tracking to-dos.")
        } else if let boardId = vm.selectedBoardId {
            VStack(spacing: 0) {
                boardHeader
                Divider().opacity(0.2)
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(alignment: .top, spacing: 12) {
                        ForEach(ProductivityColumn.allCases) { column in
                            ProductivityColumnView(
                                column: column,
                                cards: vm.cards(in: column),
                                accent: appState.themeAccent,
                                onAdd: { title in Task { await vm.addCard(to: column, title: title) } },
                                onDrop: { cardId in Task { await vm.moveCard(cardId, to: column) } },
                                onOpenSource: { jid in openJournal(jid) },
                                onRename: { id, title in Task { await vm.renameCard(id, title: title) } },
                                onDelete: { id in Task { await vm.deleteCard(id) } },
                                onToggleDone: { card in Task { await vm.toggleDone(card) } },
                            )
                            .frame(width: 280)
                        }
                    }
                    .padding(14)
                }
                .id(boardId)
            }
        } else {
            emptyState(icon: "rectangle.3.group", title: "Select a board", sub: "or create one with +.")
        }
    }

    private var boardHeader: some View {
        HStack(spacing: 8) {
            if vm.renamingBoardId == vm.selectedBoardId, vm.selectedBoardId != nil {
                TextField("Board name", text: Binding(get: { vm.renameText }, set: { vm.renameText = $0 }))
                    .textFieldStyle(.plain)
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(appState.themeText)
                    .onSubmit { Task { await vm.commitRename() } }
            } else {
                Text(vm.selectedBoard?.title ?? "Board")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(appState.themeText)
            }
            Spacer()
        }
        .padding(.horizontal, 14).padding(.vertical, 10)
    }

    private func emptyState(icon: String, title: String, sub: String) -> some View {
        VStack(spacing: 10) {
            Spacer()
            Image(systemName: icon).font(.system(size: 38)).foregroundColor(appState.themeTextSecondary.opacity(0.45))
            Text(title).font(.system(size: 14, weight: .medium)).foregroundColor(appState.themeTextSecondary)
            Text(sub).font(.system(size: 12)).foregroundColor(appState.themeTextSecondary.opacity(0.8))
            Spacer()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private func openJournal(_ journalId: String) {
        appState.clearPrimaryNav()
        appState.selectedJournalId = journalId
    }
}

// MARK: - Column

private struct ProductivityColumnView: View {
    @Environment(AppState.self) private var appState
    let column: ProductivityColumn
    let cards: [ProductivityCard]
    let accent: Color
    let onAdd: (String) -> Void
    let onDrop: (String) -> Void
    let onOpenSource: (String) -> Void
    let onRename: (String, String) -> Void
    let onDelete: (String) -> Void
    let onToggleDone: (ProductivityCard) -> Void

    @State private var adding = false
    @State private var draftTitle = ""
    @State private var dropTargeted = false
    @FocusState private var addFocused: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 6) {
                Image(systemName: column.icon).font(.system(size: 11)).foregroundColor(accent)
                Text(column.label).font(.system(size: 12, weight: .semibold)).foregroundColor(appState.themeText)
                Text("\(cards.count)").font(.system(size: 11)).foregroundColor(appState.themeTextSecondary)
                Spacer()
                Button { adding = true; addFocused = true } label: {
                    Image(systemName: "plus").font(.system(size: 11)).foregroundColor(appState.themeTextSecondary)
                }
                .buttonStyle(.plain).help("Add card")
            }
            .padding(.horizontal, 4)

            if adding {
                addRow
            }

            ForEach(cards) { card in
                ProductivityCardView(
                    card: card,
                    onOpenSource: onOpenSource,
                    onRename: onRename,
                    onDelete: onDelete,
                    onToggleDone: onToggleDone,
                )
                .draggable(card.id)
            }

            if cards.isEmpty && !adding {
                Text("Drop cards here")
                    .font(.system(size: 11)).foregroundColor(appState.themeTextSecondary.opacity(0.5))
                    .frame(maxWidth: .infinity, minHeight: 40)
            }
            Spacer(minLength: 0)
        }
        .padding(10)
        .frame(maxHeight: .infinity, alignment: .top)
        .background(
            RoundedRectangle(cornerRadius: 10)
                .fill(appState.themeCard.opacity(dropTargeted ? 0.5 : 0.28))
                .overlay(RoundedRectangle(cornerRadius: 10).stroke(accent.opacity(dropTargeted ? 0.6 : 0), lineWidth: 1.5))
        )
        .dropDestination(for: String.self) { items, _ in
            guard let id = items.first else { return false }
            onDrop(id)
            return true
        } isTargeted: { dropTargeted = $0 }
    }

    private var addRow: some View {
        HStack(spacing: 6) {
            TextField("New card", text: $draftTitle)
                .textFieldStyle(.plain)
                .font(.system(size: 12))
                .foregroundColor(appState.themeText)
                .focused($addFocused)
                .onSubmit { commit() }
            Button { commit() } label: { Image(systemName: "return").font(.system(size: 10)) }
                .buttonStyle(.plain).foregroundColor(appState.themeTextSecondary)
        }
        .padding(8)
        .background(RoundedRectangle(cornerRadius: 7).fill(appState.themeBg.opacity(0.6)))
        .onChange(of: addFocused) { _, f in if !f { commit() } }
    }

    private func commit() {
        let t = draftTitle.trimmingCharacters(in: .whitespacesAndNewlines)
        draftTitle = ""
        adding = false
        guard !t.isEmpty else { return }
        onAdd(t)
    }
}

// MARK: - Card

private struct ProductivityCardView: View {
    @Environment(AppState.self) private var appState
    let card: ProductivityCard
    let onOpenSource: (String) -> Void
    let onRename: (String, String) -> Void
    let onDelete: (String) -> Void
    let onToggleDone: (ProductivityCard) -> Void

    @State private var renaming = false
    @State private var editText = ""
    @FocusState private var focused: Bool

    private var isDone: Bool { card.boardColumn == "done" }

    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            Button { onToggleDone(card) } label: {
                Image(systemName: isDone ? "checkmark.circle.fill" : "circle")
                    .font(.system(size: 13))
                    .foregroundColor(isDone ? appState.themeAccent : appState.themeTextSecondary.opacity(0.6))
            }
            .buttonStyle(.plain)

            VStack(alignment: .leading, spacing: 4) {
                if renaming {
                    TextField("Card", text: $editText)
                        .textFieldStyle(.plain)
                        .font(.system(size: 12))
                        .foregroundColor(appState.themeText)
                        .focused($focused)
                        .onSubmit { commit() }
                        .onChange(of: focused) { _, f in if !f { commit() } }
                } else {
                    Text(card.title)
                        .font(.system(size: 12))
                        .foregroundColor(appState.themeText)
                        .strikethrough(isDone, color: appState.themeTextSecondary)
                        .opacity(isDone ? 0.6 : 1)
                        .fixedSize(horizontal: false, vertical: true)
                }
                if let jid = card.sourceJournalId {
                    Button { onOpenSource(jid) } label: {
                        HStack(spacing: 3) {
                            Image(systemName: "book.closed").font(.system(size: 8))
                            Text("From journal").font(.system(size: 9))
                        }
                        .foregroundColor(appState.themeAccent.opacity(0.85))
                    }
                    .buttonStyle(.plain)
                    .help(card.sourceExcerpt ?? "Open the source journal")
                }
            }
            Spacer(minLength: 0)
        }
        .padding(9)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 7).fill(appState.themeBg.opacity(0.65)))
        .contextMenu {
            Button("Rename") { editText = card.title; renaming = true; focused = true }
            Button("Delete", role: .destructive) { onDelete(card.id) }
        }
    }

    private func commit() {
        let t = editText.trimmingCharacters(in: .whitespacesAndNewlines)
        renaming = false
        guard !t.isEmpty, t != card.title else { return }
        onRename(card.id, t)
    }
}

// MARK: - View model

@MainActor
@Observable
final class ProductivityViewModel {
    var boards: [ProductivityBoard] = []
    var cardsAll: [ProductivityCard] = []
    var selectedBoardId: String?
    var isLoading = false
    var error: String?
    var renamingBoardId: String?
    var renameText = ""

    var selectedBoard: ProductivityBoard? { boards.first { $0.id == selectedBoardId } }

    func cards(in column: ProductivityColumn) -> [ProductivityCard] {
        cardsAll.filter { $0.boardColumn == column.rawValue }.sorted { $0.position < $1.position }
    }

    func loadBoards() async {
        isLoading = true; error = nil
        defer { isLoading = false }
        do {
            boards = try await MatchaWorkService.shared.listProductivityBoards()
            if selectedBoardId == nil { selectedBoardId = boards.first?.id }
            if let id = selectedBoardId { await loadCards(id) }
        } catch { self.error = error.localizedDescription }
    }

    func select(_ boardId: String) async {
        selectedBoardId = boardId
        await loadCards(boardId)
    }

    private func loadCards(_ boardId: String) async {
        do { cardsAll = try await MatchaWorkService.shared.listProductivityCards(boardId: boardId) }
        catch { self.error = error.localizedDescription }
    }

    func createBoard() async {
        do {
            let b = try await MatchaWorkService.shared.createProductivityBoard(title: "New board")
            await loadBoards()
            selectedBoardId = b.id
            cardsAll = []
            beginRename(b)
        } catch { self.error = error.localizedDescription }
    }

    func beginRename(_ board: ProductivityBoard) {
        selectedBoardId = board.id
        renameText = board.title
        renamingBoardId = board.id
    }

    func commitRename() async {
        guard let id = renamingBoardId else { return }
        let t = renameText.trimmingCharacters(in: .whitespacesAndNewlines)
        renamingBoardId = nil
        guard !t.isEmpty else { return }
        _ = try? await MatchaWorkService.shared.renameProductivityBoard(id: id, title: t)
        await loadBoards()
    }

    func deleteBoard(_ board: ProductivityBoard) async {
        try? await MatchaWorkService.shared.deleteProductivityBoard(id: board.id)
        if selectedBoardId == board.id { selectedBoardId = nil; cardsAll = [] }
        await loadBoards()
    }

    func addCard(to column: ProductivityColumn, title: String) async {
        guard let boardId = selectedBoardId else { return }
        do {
            let card = try await MatchaWorkService.shared.createProductivityCard(
                boardId: boardId, title: title, column: column.rawValue)
            cardsAll.append(card)
            await refreshBoardCounts()
        } catch { self.error = error.localizedDescription }
    }

    func moveCard(_ cardId: String, to column: ProductivityColumn) async {
        guard let idx = cardsAll.firstIndex(where: { $0.id == cardId }),
              cardsAll[idx].boardColumn != column.rawValue else { return }
        cardsAll[idx].boardColumn = column.rawValue       // optimistic
        do {
            let updated = try await MatchaWorkService.shared.moveProductivityCard(id: cardId, column: column.rawValue)
            if let i = cardsAll.firstIndex(where: { $0.id == cardId }) { cardsAll[i] = updated }
            await refreshBoardCounts()
        } catch {
            if let boardId = selectedBoardId { await loadCards(boardId) }
        }
    }

    func toggleDone(_ card: ProductivityCard) async {
        let target: ProductivityColumn = card.boardColumn == "done" ? .todo : .done
        await moveCard(card.id, to: target)
    }

    func renameCard(_ id: String, title: String) async {
        do {
            let updated = try await MatchaWorkService.shared.renameProductivityCard(id: id, title: title)
            if let i = cardsAll.firstIndex(where: { $0.id == id }) { cardsAll[i] = updated }
        } catch { self.error = error.localizedDescription }
    }

    func deleteCard(_ id: String) async {
        try? await MatchaWorkService.shared.deleteProductivityCard(id: id)
        cardsAll.removeAll { $0.id == id }
        await refreshBoardCounts()
    }

    /// Cheap board-list refresh so rail counts stay current after card changes.
    private func refreshBoardCounts() async {
        if let updated = try? await MatchaWorkService.shared.listProductivityBoards() { boards = updated }
    }
}
