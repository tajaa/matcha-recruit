import SwiftUI
import AppKit

/// Sidebar list of journals visible to the current user. Selection writes
/// `appState.selectedJournalId` and clears other selection slots so
/// ContentView routes to JournalDetailView. Refreshes on
/// `journalsListGeneration` bumps from sibling views (NewJournalSheet).
struct JournalListView: View {
    @Environment(AppState.self) private var appState
    @Environment(\.openWindow) private var openWindow
    var showHeader: Bool = true
    var searchText: String = ""

    @State private var journals: [MWJournal] = []
    @State private var isLoading = true
    @State private var errorMessage: String?
    /// Sidebar shows a few at a time; "Show more" reveals the next batch.
    @State private var visibleCount = 3
    private let pageSize = 3

    private func isRecentlyActive(_ dateString: String?, days: Int = 7) -> Bool {
        guard let ds = dateString, let date = parseMWDate(ds) else { return true }
        return Date().timeIntervalSince(date) < Double(days) * 86_400
    }

    var body: some View {
        VStack(spacing: 0) {
            if showHeader {
                HStack {
                    Text("Journals")
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundColor(.secondary)
                    Spacer()
                }
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                Divider().opacity(0.3)
            }

            if isLoading {
                ProgressView().tint(.secondary)
                    .frame(maxWidth: .infinity, alignment: .center)
                    .padding(.vertical, 12)
            } else if let errorMessage {
                Text(errorMessage)
                    .font(.system(size: 10))
                    .foregroundColor(.red.opacity(0.8))
                    .padding(8)
            } else if journals.isEmpty {
                VStack(spacing: 6) {
                    Image(systemName: "book.closed").font(.system(size: 22)).foregroundColor(.secondary)
                    Text("No journals yet").font(.system(size: 11)).foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity, alignment: .center)
                .padding(.vertical, 16)
            } else {
                let filtered = journals.filter { j in
                    // Bypass recency when searching so old journals remain findable.
                    let passesRecency = !searchText.isEmpty || isRecentlyActive(j.updatedAt)
                    let passesSearch = searchText.isEmpty || j.title.localizedCaseInsensitiveContains(searchText)
                    return passesRecency && passesSearch
                }
                // While searching, show all matches; otherwise paginate.
                let limit = searchText.isEmpty ? visibleCount : filtered.count
                LazyVStack(spacing: 0) {
                    ForEach(filtered.prefix(limit)) { j in
                        row(j)
                    }
                    if searchText.isEmpty && filtered.count > visibleCount {
                        SidebarShowMoreButton(
                            remaining: filtered.count - visibleCount,
                            pageSize: pageSize
                        ) { visibleCount += pageSize }
                    }
                }
                .padding(.vertical, 4)
            }
        }
        .background(Color.clear)
        .task { await load() }
        .onChange(of: appState.journalsListGeneration) { _, _ in
            Task { await load() }
        }
    }

    private func row(_ j: MWJournal) -> some View {
        let selected = appState.selectedJournalId == j.id
        return Button {
            appState.selectedJournalId = j.id
            appState.selectedThreadId = nil
            appState.selectedProjectId = nil
            appState.selectedChannelId = nil
            appState.showInbox = false
            appState.showSkills = false
        } label: {
            HStack(spacing: 8) {
                Image(systemName: j.icon ?? "book")
                    .font(.system(size: 11))
                    .foregroundColor(colorFor(j.color))
                    .frame(width: 16)
                VStack(alignment: .leading, spacing: 1) {
                    Text(j.title)
                        .font(.system(size: 12, weight: selected ? .bold : .regular))
                        .foregroundColor(appState.themeText.opacity(0.9))
                        .lineLimit(1)
                    if let n = j.entryCount, n > 0 {
                        Text("\(n) entr\(n == 1 ? "y" : "ies")")
                            .font(.system(size: 9))
                            .foregroundColor(appState.themeTextSecondary)
                    }
                }
                Spacer()
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
            .sidebarRowStyle(isSelected: selected)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .contextMenu {
            Button {
                openWindow(id: "aux", value: AuxWindowTarget.journal(j.id))
            } label: {
                Label("Open in new window", systemImage: "macwindow.on.rectangle")
            }
            Button {
                appState.splitTarget = .journal(j.id)
            } label: {
                Label("Open in split", systemImage: "rectangle.split.2x1")
            }
            Button {
                appState.bottomSplitTarget = .journal(j.id)
            } label: {
                Label("Open in bottom split", systemImage: "rectangle.split.1x2")
            }
            Divider()
            Button("Archive") {
                Task {
                    try? await JournalService.shared.archiveJournal(id: j.id)
                    await MainActor.run {
                        if appState.selectedJournalId == j.id { appState.selectedJournalId = nil }
                        appState.journalsListGeneration &+= 1
                    }
                    await load()
                }
            }
            Divider()
            Button("Delete…") {
                let alert = NSAlert()
                alert.messageText = "Delete \"\(j.title)\"?"
                alert.informativeText = "Permanently deletes the journal and all its entries. Cannot be undone."
                alert.alertStyle = .critical
                alert.addButton(withTitle: "Delete Permanently")
                alert.addButton(withTitle: "Cancel")
                if alert.runModal() == .alertFirstButtonReturn {
                    Task {
                        try? await JournalService.shared.deleteJournal(id: j.id)
                        await MainActor.run {
                            if appState.selectedJournalId == j.id { appState.selectedJournalId = nil }
                            appState.journalsListGeneration &+= 1
                        }
                        await load()
                    }
                }
            }
        }
    }

    /// Map the stored color name to a SwiftUI Color. Free-form column on
    /// the backend; constrain client-side so the picker stays sane.
    private func colorFor(_ name: String?) -> Color {
        switch name {
        case "amber": return .orange
        case "blue": return .blue
        case "purple": return .purple
        case "pink": return .pink
        case "matcha", nil, "": return appState.themeAccent
        default: return appState.themeAccent
        }
    }

    private func load() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            journals = try await MatchaWorkService.shared.listJournals(forceRefresh: true)
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

// MARK: - Journal kinds (create-time templates)

/// The journal types selectable at creation. Each seeds a starter entry on the
/// backend (see journal_service.JOURNAL_KIND_SEEDS) and gets a badge here.
enum JournalKind: String, CaseIterable, Identifiable {
    case note, blog, todo, novel, screenplay, journal
    var id: String { rawValue }

    var label: String {
        switch self {
        case .note: return "Note"
        case .blog: return "Blog"
        case .todo: return "To-dos"
        case .novel: return "Novel"
        case .screenplay: return "Screenplay"
        case .journal: return "Journal"
        }
    }
    var icon: String {
        switch self {
        case .note: return "note.text"
        case .blog: return "doc.richtext"
        case .todo: return "checklist"
        case .novel: return "books.vertical"
        case .screenplay: return "film"
        case .journal: return "book.closed"
        }
    }
    var blurb: String {
        switch self {
        case .note: return "A blank page for quick thoughts."
        case .blog: return "Title, hook, sections, CTA."
        case .todo: return "Today / this week / someday checklist."
        case .novel: return "Chapter heading + scene break."
        case .screenplay: return "Sluglines, action, dialogue."
        case .journal: return "Plain dated entries."
        }
    }
    static func from(_ raw: String?) -> JournalKind { JournalKind(rawValue: raw ?? "journal") ?? .journal }

    // MARK: - Workspace behavior

    /// A document opens straight into one editor (single body entry). Only the
    /// diary `.journal` kind keeps the dated-entries timeline.
    var isDocKind: Bool { self != .journal }

    /// Screenplays use the dedicated Final-Draft-style element editor + Fountain
    /// storage instead of the shared markdown editor.
    var usesScreenplayEditor: Bool { self == .screenplay }

    /// Default editor typography for the markdown kinds (screenplay overrides
    /// this with Courier inside its own editor).
    var defaultFontFamily: String {
        switch self {
        case .novel, .blog: return "serif"
        default: return "system"
        }
    }

    /// Blocks offered by the "/" slash menu in the markdown editor. Screenplay
    /// is empty — it drives formatting through Tab/Enter element cycling.
    var slashBlocks: [SlashBlock] {
        switch self {
        case .blog:
            return [.heading, .subheading, .image, .quote, .divider, .bullet, .numbered, .code, .link]
        case .novel:
            return [.chapter, .sceneBreak, .quote, .image]
        case .note:
            return [.heading, .bullet, .todo, .quote, .code, .image, .divider, .link]
        case .todo:
            return [.todo, .heading, .bullet, .divider]
        case .journal:
            return [.heading, .bullet, .todo, .quote, .image, .divider]
        case .screenplay:
            return []
        }
    }
}

// MARK: - Slash command blocks

/// One entry in the editor's "/" slash menu. `insert` says how committing the
/// block mutates the text; `keywords` widen fuzzy filtering beyond the title.
struct SlashBlock: Identifiable, Hashable {
    let id: String
    let title: String
    let subtitle: String
    let icon: String
    let keywords: [String]
    let insert: SlashInsert
}

/// How a chosen slash block edits the document.
enum SlashInsert: Hashable {
    case linePrefix(String)   // toggle/prepend a line prefix ("## ", "- [ ] ", "> ")
    case snippet(String)      // drop a raw block at the caret ("\n---\n", code fence)
    case image                // run the image picker/upload path
    case link                 // insert/wrap a [text](url) link
}

extension SlashBlock {
    static let heading    = SlashBlock(id: "heading",    title: "Heading",        subtitle: "Section heading",     icon: "textformat.size",                        keywords: ["h2", "section"],        insert: .linePrefix("## "))
    static let subheading = SlashBlock(id: "subheading", title: "Subheading",     subtitle: "Smaller heading",     icon: "textformat",                             keywords: ["h3"],                   insert: .linePrefix("### "))
    static let bullet     = SlashBlock(id: "bullet",     title: "Bulleted list",  subtitle: "Unordered list item", icon: "list.bullet",                            keywords: ["ul", "list"],           insert: .linePrefix("- "))
    static let numbered   = SlashBlock(id: "numbered",   title: "Numbered list",  subtitle: "Ordered list item",   icon: "list.number",                            keywords: ["ol", "ordered"],        insert: .linePrefix("1. "))
    static let todo       = SlashBlock(id: "todo",       title: "To-do",          subtitle: "Checkbox item",       icon: "checklist",                              keywords: ["task", "checkbox"],     insert: .linePrefix("- [ ] "))
    static let quote      = SlashBlock(id: "quote",      title: "Quote",          subtitle: "Block quote",         icon: "text.quote",                             keywords: ["blockquote"],           insert: .linePrefix("> "))
    static let code       = SlashBlock(id: "code",       title: "Code block",     subtitle: "Fenced code",         icon: "chevron.left.forwardslash.chevron.right", keywords: ["pre", "monospace"],     insert: .snippet("\n```\ncode\n```\n"))
    static let divider    = SlashBlock(id: "divider",    title: "Divider",        subtitle: "Horizontal rule",     icon: "minus",                                  keywords: ["hr", "rule", "break"],  insert: .snippet("\n---\n"))
    static let image      = SlashBlock(id: "image",      title: "Image",          subtitle: "Upload or drop a file", icon: "photo",                                keywords: ["picture", "media", "img"], insert: .image)
    static let link       = SlashBlock(id: "link",       title: "Link",           subtitle: "Insert a hyperlink",  icon: "link",                                   keywords: ["url", "href"],          insert: .link)
    static let chapter    = SlashBlock(id: "chapter",    title: "Chapter",        subtitle: "New chapter heading", icon: "book",                                   keywords: ["heading"],              insert: .linePrefix("# Chapter "))
    static let sceneBreak = SlashBlock(id: "sceneBreak", title: "Scene break",    subtitle: "Section divider",     icon: "arrow.left.and.right",                   keywords: ["divider", "hr"],        insert: .snippet("\n---\n"))
}

// MARK: - Journals hub (the Obsidian-style parent module)

/// Full-pane "Journals" hub. Left: a folder tree (company-scoped adjacency
/// list). Right: the journals filed in the selected folder, as cards. This is
/// what the sidebar "Journals" header opens; picking a journal card sets
/// `selectedJournalId` so JournalDetailView opens over the hub (it stays set,
/// so closing the journal returns here).
struct JournalsLibraryView: View {
    @Environment(AppState.self) private var appState
    @Environment(\.openWindow) private var openWindow

    @State private var folders: [MWJournalFolder] = []
    @State private var journals: [MWJournal] = []
    @State private var selectedFolderId: String? = nil   // nil = All
    @State private var unfiledSelected = false            // the "Unfiled" node
    @State private var collapsed: Set<String> = []
    @State private var isLoading = true
    @State private var errorMessage: String?
    @State private var showNewJournal = false
    @State private var renamingFolder: MWJournalFolder?
    @State private var renameText = ""

    private let columns = [GridItem(.adaptive(minimum: 190, maximum: 260), spacing: 14)]

    var body: some View {
        HSplitView {
            folderRail
                .frame(minWidth: 200, idealWidth: 230, maxWidth: 300)
            Group {
                if let jid = appState.selectedJournalId {
                    // Embed the open journal in the right pane so the folder
                    // rail stays put — pick a folder to come back to the grid.
                    JournalDetailView(journalId: jid)
                } else {
                    mainArea
                }
            }
            .frame(minWidth: 380, maxWidth: .infinity, maxHeight: .infinity)
        }
        .background(ThemeRadialBackground())
        .task { await load() }
        .onChange(of: appState.journalsListGeneration) { _, _ in Task { await load() } }
        .sheet(isPresented: $showNewJournal) {
            NewJournalSheet(initialFolderId: effectiveFolderId) { journal in
                appState.journalsListGeneration &+= 1
                appState.selectedJournalId = journal.id   // open the new journal
            }
            .environment(appState)
        }
        .sheet(item: $renamingFolder) { folder in
            renameSheet(folder)
        }
    }

    /// Folder to file a new journal into given the current selection.
    private var effectiveFolderId: String? { unfiledSelected ? nil : selectedFolderId }

    // ── Folder rail ─────────────────────────────────────────────────────

    private var folderRail: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Text("Library")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundColor(appState.themeTextSecondary)
                Spacer()
                Button { Task { await newFolder(parent: nil) } } label: {
                    Image(systemName: "folder.badge.plus").font(.system(size: 12))
                }
                .buttonStyle(.plain)
                .foregroundColor(appState.themeTextSecondary)
                .help("New folder")
            }
            .padding(.horizontal, 14)
            .padding(.top, 14)
            .padding(.bottom, 8)

            ScrollView {
                LazyVStack(alignment: .leading, spacing: 1) {
                    folderRow(title: "All Journals", icon: "tray.full",
                              count: journals.count, isSelected: selectedFolderId == nil && !unfiledSelected,
                              depth: 0) {
                        selectedFolderId = nil; unfiledSelected = false
                        appState.selectedJournalId = nil
                    }
                    ForEach(visibleFolders, id: \.0.id) { pair in
                        folderTreeRow(pair.0, depth: pair.1)
                    }
                    let unfiled = journals.filter { $0.folderId == nil }.count
                    if unfiled > 0 {
                        folderRow(title: "Unfiled", icon: "tray",
                                  count: unfiled, isSelected: unfiledSelected, depth: 0) {
                            unfiledSelected = true; selectedFolderId = nil
                            appState.selectedJournalId = nil
                        }
                    }
                }
                .padding(.horizontal, 8)
                .padding(.bottom, 12)
            }
        }
        .frame(maxHeight: .infinity, alignment: .top)
        .background(appState.themeSidebar.opacity(0.5))
    }

    /// DFS-ordered (folder, depth) honoring collapse state.
    private var visibleFolders: [(MWJournalFolder, Int)] {
        var out: [(MWJournalFolder, Int)] = []
        func walk(_ parent: String?, _ depth: Int) {
            let kids = folders.filter { $0.parentId == parent }
                .sorted { $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending }
            for k in kids {
                out.append((k, depth))
                if !collapsed.contains(k.id) { walk(k.id, depth + 1) }
            }
        }
        walk(nil, 0)
        return out
    }

    private func hasChildren(_ id: String) -> Bool { folders.contains { $0.parentId == id } }

    @ViewBuilder
    private func folderTreeRow(_ folder: MWJournalFolder, depth: Int) -> some View {
        let isSel = selectedFolderId == folder.id && !unfiledSelected
        let count = journals.filter { $0.folderId == folder.id }.count
        HStack(spacing: 4) {
            if hasChildren(folder.id) {
                Button {
                    if collapsed.contains(folder.id) { collapsed.remove(folder.id) }
                    else { collapsed.insert(folder.id) }
                } label: {
                    Image(systemName: collapsed.contains(folder.id) ? "chevron.right" : "chevron.down")
                        .font(.system(size: 8, weight: .semibold))
                        .foregroundColor(appState.themeTextSecondary)
                        .frame(width: 10)
                }
                .buttonStyle(.plain)
            } else {
                Spacer().frame(width: 10)
            }
            folderRow(title: folder.name, icon: "folder", count: count,
                      isSelected: isSel, depth: depth, inset: false) {
                selectedFolderId = folder.id; unfiledSelected = false
                appState.selectedJournalId = nil
            }
        }
        .padding(.leading, CGFloat(depth) * 12)
        .contextMenu {
            Button("New subfolder") { Task { await newFolder(parent: folder.id) } }
            Button("Rename…") { renameText = folder.name; renamingFolder = folder }
            Divider()
            Button("Delete folder", role: .destructive) { Task { await deleteFolder(folder) } }
        }
    }

    @ViewBuilder
    private func folderRow(title: String, icon: String, count: Int, isSelected: Bool,
                           depth: Int, inset: Bool = true, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 7) {
                Image(systemName: icon)
                    .font(.system(size: 11))
                    .foregroundColor(isSelected ? appState.themeAccent : appState.themeTextSecondary)
                    .frame(width: 15)
                Text(title)
                    .font(.system(size: 12, weight: isSelected ? .semibold : .regular))
                    .foregroundColor(appState.themeText.opacity(0.92))
                    .lineLimit(1)
                Spacer(minLength: 4)
                if count > 0 {
                    Text("\(count)")
                        .font(.system(size: 10))
                        .foregroundColor(appState.themeTextSecondary)
                }
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 5)
            .background(
                RoundedRectangle(cornerRadius: 6)
                    .fill(isSelected ? appState.themeAccent.opacity(0.14) : Color.clear)
            )
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    // ── Main area (journal cards) ───────────────────────────────────────

    private var mainArea: some View {
        VStack(spacing: 0) {
            HStack(alignment: .center) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(headerTitle)
                        .font(.system(size: 20, weight: .bold))
                        .foregroundColor(appState.themeText)
                    Text("\(shownJournals.count) journal\(shownJournals.count == 1 ? "" : "s")")
                        .font(.system(size: 12))
                        .foregroundColor(appState.themeTextSecondary)
                }
                Spacer()
                Button { showNewJournal = true } label: {
                    HStack(spacing: 5) {
                        Image(systemName: "plus")
                        Text("New Journal").font(.system(size: 12, weight: .semibold))
                    }
                    .padding(.horizontal, 12).padding(.vertical, 7)
                    .background(appState.themeAccent)
                    .foregroundColor(appState.themeOnAccent)
                    .cornerRadius(8)
                }
                .buttonStyle(.plain)
            }
            .padding(20)

            Divider().background(appState.themeBorder)

            if isLoading {
                Spacer()
                ProgressView().tint(appState.themeTextSecondary)
                Spacer()
            } else if let errorMessage {
                Spacer()
                Text(errorMessage).font(.system(size: 12)).foregroundColor(.red.opacity(0.8))
                Spacer()
            } else if shownJournals.isEmpty {
                emptyState
            } else {
                ScrollView {
                    LazyVGrid(columns: columns, spacing: 14) {
                        ForEach(shownJournals) { j in journalCard(j) }
                    }
                    .padding(20)
                }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private var headerTitle: String {
        if unfiledSelected { return "Unfiled" }
        if let id = selectedFolderId, let f = folders.first(where: { $0.id == id }) { return f.name }
        return "All Journals"
    }

    private var shownJournals: [MWJournal] {
        _ = JournalStarStore.shared.generation
        let base: [MWJournal]
        if unfiledSelected { base = journals.filter { $0.folderId == nil } }
        else if let id = selectedFolderId { base = journals.filter { $0.folderId == id } }
        else { base = journals }
        let stars = JournalStarStore.shared
        return base.sorted { stars.isStarred($0.id) && !stars.isStarred($1.id) }
    }

    private var emptyState: some View {
        VStack(spacing: 10) {
            Spacer()
            Image(systemName: "books.vertical").font(.system(size: 34)).foregroundColor(appState.themeTextSecondary)
            Text("No journals here yet").font(.system(size: 14, weight: .medium)).foregroundColor(appState.themeText)
            Text("Create one with a template — note, blog, to-dos, novel, or screenplay.")
                .font(.system(size: 12)).foregroundColor(appState.themeTextSecondary)
            Button { showNewJournal = true } label: {
                Text("New Journal").font(.system(size: 12, weight: .semibold))
                    .padding(.horizontal, 14).padding(.vertical, 7)
                    .background(appState.themeAccent).foregroundColor(appState.themeOnAccent).cornerRadius(8)
            }
            .buttonStyle(.plain)
            .padding(.top, 4)
            Spacer()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private func journalCard(_ j: MWJournal) -> some View {
        let kind = JournalKind.from(j.kind)
        _ = JournalStarStore.shared.generation   // re-render on star changes
        let starred = JournalStarStore.shared.isStarred(j.id)
        return Button {
            appState.selectedJournalId = j.id   // hub stays set → back returns here
        } label: {
            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    Image(systemName: j.icon ?? kind.icon)
                        .font(.system(size: 16))
                        .foregroundColor(colorFor(j.color))
                    Spacer()
                    if starred {
                        Image(systemName: "star.fill").font(.system(size: 10)).foregroundColor(appState.themeAccent)
                    }
                    Text(kind.label.uppercased())
                        .font(.system(size: 8, weight: .bold))
                        .tracking(0.5)
                        .foregroundColor(appState.themeTextSecondary)
                        .padding(.horizontal, 6).padding(.vertical, 2)
                        .background(Capsule().fill(appState.themeAccent.opacity(0.10)))
                }
                Text(j.title)
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(appState.themeText)
                    .lineLimit(2)
                    .frame(maxWidth: .infinity, alignment: .leading)
                if let d = j.description, !d.isEmpty {
                    Text(d).font(.system(size: 11)).foregroundColor(appState.themeTextSecondary)
                        .lineLimit(2).frame(maxWidth: .infinity, alignment: .leading)
                }
                Spacer(minLength: 0)
                Text("\(j.entryCount ?? 0) entr\((j.entryCount ?? 0) == 1 ? "y" : "ies")")
                    .font(.system(size: 10)).foregroundColor(appState.themeTextSecondary)
            }
            .padding(14)
            .frame(height: 130, alignment: .topLeading)
            .elevatedCard(cornerRadius: 12)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .contextMenu { cardMenu(j) }
    }

    @ViewBuilder
    private func cardMenu(_ j: MWJournal) -> some View {
        Button(JournalStarStore.shared.isStarred(j.id) ? "Unstar" : "Star") {
            JournalStarStore.shared.toggle(j.id)
        }
        Divider()
        Menu("Move to") {
            Button("Root (unfiled)") { Task { await move(j, to: nil) } }
            Divider()
            ForEach(folders.sorted { $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending }) { f in
                Button(f.name) { Task { await move(j, to: f.id) } }
            }
        }
        Divider()
        Button { openWindow(id: "aux", value: AuxWindowTarget.journal(j.id)) } label: {
            Label("Open in new window", systemImage: "macwindow.on.rectangle")
        }
        Button { appState.splitTarget = .journal(j.id) } label: {
            Label("Open in split", systemImage: "rectangle.split.2x1")
        }
        Divider()
        Button("Archive") {
            Task {
                try? await JournalService.shared.archiveJournal(id: j.id)
                appState.journalsListGeneration &+= 1
                await load()
            }
        }
    }

    private func renameSheet(_ folder: MWJournalFolder) -> some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Rename folder").font(.system(size: 14, weight: .semibold)).foregroundColor(appState.themeText)
            TextField("Folder name", text: $renameText)
                .textFieldStyle(.roundedBorder)
            HStack {
                Spacer()
                Button("Cancel") { renamingFolder = nil }.buttonStyle(.plain)
                Button("Save") {
                    let name = renameText.trimmingCharacters(in: .whitespaces)
                    let id = folder.id
                    renamingFolder = nil
                    guard !name.isEmpty else { return }
                    Task {
                        _ = try? await MatchaWorkService.shared.renameJournalFolder(id: id, name: name)
                        await load()
                    }
                }
                .keyboardShortcut(.return)
            }
        }
        .padding(18)
        .frame(width: 320)
        .background(appState.themeBg)
    }

    private func colorFor(_ name: String?) -> Color {
        switch name {
        case "amber": return .orange
        case "blue": return .blue
        case "purple": return .purple
        case "pink": return .pink
        default: return appState.themeAccent
        }
    }

    // ── Data ────────────────────────────────────────────────────────────

    private func load() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            async let f = MatchaWorkService.shared.listJournalFolders()
            async let j = MatchaWorkService.shared.listJournals(forceRefresh: true)
            folders = try await f
            journals = try await j
            // Drop a stale selection if its folder was deleted elsewhere.
            if let id = selectedFolderId, !folders.contains(where: { $0.id == id }) {
                selectedFolderId = nil
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func newFolder(parent: String?) async {
        do {
            _ = try await MatchaWorkService.shared.createJournalFolder(name: "New Folder", parentId: parent)
            if let parent { collapsed.remove(parent) }
            await load()
        } catch { errorMessage = error.localizedDescription }
    }

    private func deleteFolder(_ folder: MWJournalFolder) async {
        do {
            try await MatchaWorkService.shared.deleteJournalFolder(id: folder.id)
            if selectedFolderId == folder.id { selectedFolderId = nil }
            appState.journalsListGeneration &+= 1   // journals SET NULL → refresh sidebar too
            await load()
        } catch { errorMessage = error.localizedDescription }
    }

    private func move(_ j: MWJournal, to folderId: String?) async {
        do {
            _ = try await MatchaWorkService.shared.moveJournal(id: j.id, folderId: folderId)
            appState.journalsListGeneration &+= 1
            await load()
        } catch { errorMessage = error.localizedDescription }
    }
}

// MARK: - Sidebar document tree

/// Backing model for the persistent Journals tree in the app sidebar
/// (Obsidian/Scrivener-style: folders + documents nested, always visible). The
/// flattened, DFS-ordered rows are precomputed in `rebuild()` — never in a
/// SwiftUI body — so the sidebar LazyVStack stays cheap as the document count
/// grows. Folder CRUD + document moves reuse the existing service methods.
@MainActor
@Observable
final class JournalSidebarModel {
    var folders: [MWJournalFolder] = []
    var journals: [MWJournal] = []
    var expanded: Set<String> = []
    var isLoading = false
    var error: String?
    private(set) var rows: [Row] = []

    enum RowKind: Hashable { case folder(MWJournalFolder); case doc(MWJournal) }
    struct Row: Identifiable, Hashable {
        let id: String        // "f:<id>" for folders, "d:<id>" for documents
        let kind: RowKind
        let depth: Int
    }

    func load() async {
        isLoading = true
        error = nil
        defer { isLoading = false }
        do {
            async let f = MatchaWorkService.shared.listJournalFolders()
            async let j = MatchaWorkService.shared.listJournals(forceRefresh: true)
            folders = try await f
            journals = try await j
            // Forget expansion of folders that no longer exist.
            expanded = expanded.intersection(Set(folders.map { $0.id }))
            rebuild()
        } catch {
            self.error = error.localizedDescription
        }
    }

    func toggle(_ folderId: String) {
        if expanded.contains(folderId) { expanded.remove(folderId) } else { expanded.insert(folderId) }
        rebuild()
    }

    func hasChildren(_ folderId: String) -> Bool {
        folders.contains { $0.parentId == folderId } || journals.contains { $0.folderId == folderId }
    }

    /// Flatten the tree honoring collapse state: each folder, then (if expanded)
    /// its subfolders and its documents; unfiled documents trail at the root.
    func rebuild() {
        var out: [Row] = []
        func walk(_ parentId: String?, _ depth: Int) {
            let childFolders = folders.filter { $0.parentId == parentId }
                .sorted { $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending }
            for f in childFolders {
                out.append(Row(id: "f:\(f.id)", kind: .folder(f), depth: depth))
                if expanded.contains(f.id) {
                    walk(f.id, depth + 1)
                    let docs = journals.filter { $0.folderId == f.id }
                        .sorted { $0.title.localizedCaseInsensitiveCompare($1.title) == .orderedAscending }
                    for d in docs { out.append(Row(id: "d:\(d.id)", kind: .doc(d), depth: depth + 1)) }
                }
            }
            if parentId == nil {
                let rootDocs = journals.filter { $0.folderId == nil }
                    .sorted { $0.title.localizedCaseInsensitiveCompare($1.title) == .orderedAscending }
                for d in rootDocs { out.append(Row(id: "d:\(d.id)", kind: .doc(d), depth: 0)) }
            }
        }
        walk(nil, 0)
        rows = out
    }
}
