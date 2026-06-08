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

// MARK: - Journals workspace (macOS Notes / Evernote, three columns)

/// The Journals surface: folder rail · note list (title + snippet + modified
/// date) · document editor. Folders are colorable + nestable; notes are
/// color-coded by document type and open in the embedded per-kind editor
/// (markdown or screenplay). The col-3 selection is LOCAL — picking a note must
/// not route the primary pane away from this workspace.
struct JournalsWorkspace: View {
    @Environment(AppState.self) private var appState

    enum FolderMode: Equatable { case all, starred, folder(String) }
    enum SortKey: String, CaseIterable { case modified = "Date Modified", created = "Date Created", title = "Title" }

    @State private var folders: [MWJournalFolder] = []
    @State private var journals: [MWJournal] = []
    @State private var mode: FolderMode = .all
    @State private var collapsed: Set<String> = []
    @State private var sort: SortKey = .modified
    @State private var search = ""
    @State private var selectedJournalId: String? = nil       // local col-3 selection
    @State private var renamingFolderId: String? = nil
    @State private var renamingJournalId: String? = nil
    @State private var renameText = ""
    @State private var isLoading = true
    @State private var errorMessage: String?
    @State private var folderRailCollapsed = false
    @FocusState private var renameFocused: Bool

    private static let relFmt: RelativeDateTimeFormatter = {
        let f = RelativeDateTimeFormatter(); f.unitsStyle = .abbreviated; return f
    }()
    private let palette = ["matcha", "blue", "purple", "pink", "amber", "red", "teal", "gray"]

    var body: some View {
        HSplitView {
            if folderRailCollapsed {
                MWHubRailStrip { folderRailCollapsed = false }
            } else {
                folderRail.frame(minWidth: 180, idealWidth: 210, maxWidth: 260)
            }
            noteList.frame(minWidth: 250, idealWidth: 290, maxWidth: 380)
            editorPane.frame(minWidth: 380, maxWidth: .infinity, maxHeight: .infinity)
        }
        .background(ThemeRadialBackground())
        .task {
            await load()
            if let jid = appState.selectedJournalId { selectedJournalId = jid; ensureModeFor(jid) }
        }
        .onChange(of: appState.journalsListGeneration) { _, _ in Task { await load() } }
        .onChange(of: appState.selectedJournalId) { _, v in
            if let v { selectedJournalId = v; ensureModeFor(v) }
        }
        .onChange(of: selectedJournalId) { _, _ in
            // After leaving an edited note, re-sort the list by recent edit
            // (the backend bumps the journal's updated_at on entry save).
            Task { try? await Task.sleep(for: .milliseconds(700)); await refreshNotes() }
        }
    }

    // ── Folder rail ─────────────────────────────────────────────────────

    private var folderRail: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Text("Folders")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundColor(appState.themeTextSecondary)
                Spacer()
                Button { folderRailCollapsed = true } label: {
                    Image(systemName: "sidebar.left").font(.system(size: 12))
                }
                .buttonStyle(.plain)
                .foregroundColor(appState.themeTextSecondary)
                .help("Hide sidebar")
                Button { Task { await newFolder(parent: nil) } } label: {
                    Image(systemName: "folder.badge.plus").font(.system(size: 12))
                }
                .buttonStyle(.plain)
                .foregroundColor(appState.themeTextSecondary)
                .help("New folder")
            }
            .padding(.horizontal, 14).padding(.top, 14).padding(.bottom, 8)

            ScrollView {
                LazyVStack(alignment: .leading, spacing: 1) {
                    fixedRow(title: "All Notes", icon: "tray.full", selected: mode == .all) { mode = .all }
                    fixedRow(title: "Starred", icon: "star", selected: mode == .starred) { mode = .starred }
                    if !folders.isEmpty {
                        Divider().padding(.horizontal, 8).padding(.vertical, 4)
                    }
                    ForEach(visibleFolders, id: \.0.id) { pair in
                        folderTreeRow(pair.0, depth: pair.1)
                    }
                }
                .padding(.horizontal, 8).padding(.bottom, 12)
            }
        }
        .frame(maxHeight: .infinity, alignment: .top)
        .background(appState.themeSidebar.opacity(0.5))
    }

    private func fixedRow(title: String, icon: String, selected: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 7) {
                Image(systemName: icon)
                    .font(.system(size: 11))
                    .foregroundColor(selected ? appState.themeAccent : appState.themeTextSecondary)
                    .frame(width: 15)
                Text(title)
                    .font(.system(size: 12, weight: selected ? .semibold : .regular))
                    .foregroundColor(appState.themeText.opacity(0.92))
                Spacer(minLength: 0)
            }
            .padding(.horizontal, 8).padding(.vertical, 5)
            .background(RoundedRectangle(cornerRadius: 6).fill(selected ? appState.themeAccent.opacity(0.14) : Color.clear))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
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
        let isSel = mode == .folder(folder.id)
        HStack(spacing: 4) {
            if hasChildren(folder.id) {
                Button { toggle(folder.id) } label: {
                    Image(systemName: collapsed.contains(folder.id) ? "chevron.right" : "chevron.down")
                        .font(.system(size: 8, weight: .semibold))
                        .foregroundColor(appState.themeTextSecondary)
                        .frame(width: 10)
                }
                .buttonStyle(.plain)
            } else {
                Spacer().frame(width: 10)
            }
            if renamingFolderId == folder.id {
                TextField("Folder", text: $renameText)
                    .textFieldStyle(.plain)
                    .font(.system(size: 12))
                    .foregroundColor(appState.themeText)
                    .focused($renameFocused)
                    .onSubmit { Task { await commitFolderRename(folder.id) } }
                    .onChange(of: renameFocused) { _, f in
                        if !f, renamingFolderId == folder.id { Task { await commitFolderRename(folder.id) } }
                    }
                    .padding(.vertical, 5)
            } else {
                Button { mode = .folder(folder.id) } label: {
                    HStack(spacing: 7) {
                        Image(systemName: "folder.fill")
                            .font(.system(size: 11))
                            .foregroundColor(iconColor(folder.color, fallback: appState.themeTextSecondary))
                            .frame(width: 15)
                        Text(folder.name)
                            .font(.system(size: 12, weight: isSel ? .semibold : .regular))
                            .foregroundColor(appState.themeText.opacity(0.92))
                            .lineLimit(1)
                        Spacer(minLength: 0)
                    }
                    .padding(.horizontal, 8).padding(.vertical, 5)
                    .background(RoundedRectangle(cornerRadius: 6).fill(isSel ? appState.themeAccent.opacity(0.14) : Color.clear))
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .simultaneousGesture(TapGesture(count: 2).onEnded { startFolderRename(folder) })
                .contextMenu {
                    Button("New subfolder") { Task { await newFolder(parent: folder.id) } }
                    Button("Rename…") { startFolderRename(folder) }
                    colorMenu { c in Task { await setFolderColor(folder, c) } }
                    Divider()
                    Button("Delete folder", role: .destructive) { Task { await deleteFolder(folder) } }
                }
            }
        }
        .padding(.leading, CGFloat(depth) * 12)
    }

    // ── Note list (col 2) ───────────────────────────────────────────────

    private var noteList: some View {
        VStack(spacing: 0) {
            VStack(spacing: 8) {
                HStack(spacing: 6) {
                    Image(systemName: "magnifyingglass").font(.system(size: 11)).foregroundColor(appState.themeTextSecondary)
                    TextField("Search", text: $search)
                        .textFieldStyle(.plain).font(.system(size: 12)).foregroundColor(appState.themeText)
                }
                .padding(.horizontal, 8).padding(.vertical, 5)
                .background(RoundedRectangle(cornerRadius: 6).fill(appState.themeCard.opacity(0.6)))

                HStack(spacing: 8) {
                    Text(listTitle).font(.system(size: 13, weight: .bold)).foregroundColor(appState.themeText).lineLimit(1)
                    Spacer()
                    Menu {
                        ForEach(SortKey.allCases, id: \.self) { s in
                            Button { sort = s } label: { Label(s.rawValue, systemImage: sort == s ? "checkmark" : "") }
                        }
                    } label: {
                        Image(systemName: "arrow.up.arrow.down").font(.system(size: 11)).foregroundColor(appState.themeTextSecondary)
                    }
                    .menuStyle(.borderlessButton).menuIndicator(.hidden).fixedSize()
                    .help("Sort")
                    Menu {
                        ForEach(JournalKind.allCases) { k in
                            Button { Task { await createNote(k) } } label: { Label(k.label, systemImage: k.icon) }
                        }
                    } label: {
                        Image(systemName: "square.and.pencil").font(.system(size: 13)).foregroundColor(appState.themeAccent)
                    }
                    .menuStyle(.borderlessButton).menuIndicator(.hidden).fixedSize()
                    .help("New note")
                }
            }
            .padding(.horizontal, 12).padding(.top, 12).padding(.bottom, 8)
            Divider().opacity(0.2)

            if isLoading {
                Spacer(); ProgressView().tint(appState.themeTextSecondary); Spacer()
            } else if let errorMessage {
                Spacer()
                Text(errorMessage).font(.system(size: 11)).foregroundColor(.red.opacity(0.8)).padding(12)
                Spacer()
            } else if shownNotes.isEmpty {
                noteEmptyState
            } else {
                ScrollView {
                    LazyVStack(spacing: 1) {
                        ForEach(shownNotes) { j in noteRow(j) }
                    }
                    .padding(.vertical, 4).padding(.horizontal, 6)
                }
            }
        }
        .frame(maxHeight: .infinity, alignment: .top)
        .background(appState.themeBg.opacity(0.3))
    }

    private func noteRow(_ j: MWJournal) -> some View {
        let kind = JournalKind.from(j.kind)
        let selected = selectedJournalId == j.id
        _ = JournalStarStore.shared.generation
        return Button { selectedJournalId = j.id } label: {
            HStack(alignment: .top, spacing: 9) {
                Image(systemName: j.icon ?? kind.icon)
                    .font(.system(size: 14))
                    .foregroundColor(iconColor(j.color, fallback: appState.themeAccent))
                    .frame(width: 18)
                VStack(alignment: .leading, spacing: 2) {
                    if renamingJournalId == j.id {
                        TextField("Title", text: $renameText)
                            .textFieldStyle(.plain)
                            .font(.system(size: 13, weight: .semibold))
                            .foregroundColor(appState.themeText)
                            .focused($renameFocused)
                            .onSubmit { Task { await commitNoteRename(j.id) } }
                            .onChange(of: renameFocused) { _, f in
                                if !f, renamingJournalId == j.id { Task { await commitNoteRename(j.id) } }
                            }
                    } else {
                        HStack(spacing: 5) {
                            Text(j.title.isEmpty ? "Untitled" : j.title)
                                .font(.system(size: 13, weight: .semibold))
                                .foregroundColor(appState.themeText)
                                .lineLimit(1)
                            if JournalStarStore.shared.isStarred(j.id) {
                                Image(systemName: "star.fill").font(.system(size: 8)).foregroundColor(appState.themeAccent)
                            }
                        }
                    }
                    if let p = j.preview, !p.isEmpty {
                        Text(p).font(.system(size: 11)).foregroundColor(appState.themeTextSecondary)
                            .lineLimit(2).multilineTextAlignment(.leading)
                    }
                    Text(modifiedLabel(j.updatedAt))
                        .font(.system(size: 10)).foregroundColor(appState.themeTextSecondary.opacity(0.8))
                }
                Spacer(minLength: 0)
            }
            .padding(.horizontal, 12).padding(.vertical, 8)
            .background(RoundedRectangle(cornerRadius: 6).fill(selected ? appState.themeAccent.opacity(0.14) : Color.clear))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .simultaneousGesture(TapGesture(count: 2).onEnded { startNoteRename(j) })
        .contextMenu { noteMenu(j) }
    }

    @ViewBuilder
    private func noteMenu(_ j: MWJournal) -> some View {
        Button("Rename") { startNoteRename(j) }
        colorMenu { c in Task { await setNoteColor(j, c) } }
        Menu("Move to") {
            Button("None (unfiled)") { Task { await move(j, to: nil) } }
            if !folders.isEmpty { Divider() }
            ForEach(folders.sorted { $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending }) { f in
                Button(f.name) { Task { await move(j, to: f.id) } }
            }
        }
        Button(JournalStarStore.shared.isStarred(j.id) ? "Unstar" : "Star") { JournalStarStore.shared.toggle(j.id) }
        Divider()
        AuxOpenMenuButtons(target: .journal(j.id))
        Divider()
        Button("Archive") { Task { await archive(j) } }
        Button("Delete…", role: .destructive) { confirmDelete(j) }
    }

    @ViewBuilder
    private func colorMenu(_ pick: @escaping (String) -> Void) -> some View {
        Menu("Color") {
            ForEach(palette, id: \.self) { name in
                Button(name.capitalized) { pick(name) }
            }
        }
    }

    private var noteEmptyState: some View {
        VStack(spacing: 8) {
            Spacer()
            Image(systemName: "note.text").font(.system(size: 26)).foregroundColor(appState.themeTextSecondary.opacity(0.6))
            Text(search.isEmpty ? "No notes here" : "No matches")
                .font(.system(size: 12)).foregroundColor(appState.themeTextSecondary)
            Spacer()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    // ── Editor (col 3) ──────────────────────────────────────────────────

    @ViewBuilder
    private var editorPane: some View {
        if let jid = selectedJournalId {
            JournalDetailView(journalId: jid, isEmbedded: true)
        } else {
            VStack(spacing: 10) {
                Spacer()
                Image(systemName: "doc.text").font(.system(size: 40)).foregroundColor(appState.themeTextSecondary.opacity(0.45))
                Text("Select a note").font(.system(size: 14, weight: .medium)).foregroundColor(appState.themeTextSecondary)
                Text("or create one with the pencil button.").font(.system(size: 12)).foregroundColor(appState.themeTextSecondary.opacity(0.8))
                Spacer()
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(Color.appBackground)
        }
    }

    // ── Derived ─────────────────────────────────────────────────────────

    private var listTitle: String {
        switch mode {
        case .all: return "All Notes"
        case .starred: return "Starred"
        case .folder(let id): return folders.first { $0.id == id }?.name ?? "Folder"
        }
    }

    private var currentFolderId: String? {
        if case .folder(let id) = mode { return id }
        return nil
    }

    private var shownNotes: [MWJournal] {
        _ = JournalStarStore.shared.generation
        var base: [MWJournal]
        switch mode {
        case .all: base = journals
        case .starred: base = journals.filter { JournalStarStore.shared.isStarred($0.id) }
        case .folder(let id): base = journals.filter { $0.folderId == id }
        }
        if !search.isEmpty {
            base = base.filter {
                $0.title.localizedCaseInsensitiveContains(search)
                    || ($0.preview ?? "").localizedCaseInsensitiveContains(search)
            }
        }
        switch sort {
        case .modified: base.sort { ($0.updatedAt ?? "") > ($1.updatedAt ?? "") }
        case .created:  base.sort { ($0.createdAt ?? "") > ($1.createdAt ?? "") }
        case .title:    base.sort { $0.title.localizedCaseInsensitiveCompare($1.title) == .orderedAscending }
        }
        return base
    }

    private func modifiedLabel(_ iso: String?) -> String {
        guard let iso, let d = parseMWDate(iso) else { return "" }
        return Self.relFmt.localizedString(for: d, relativeTo: Date())
    }

    private func paletteColor(_ name: String) -> Color {
        switch name {
        case "blue": return .blue
        case "purple": return .purple
        case "pink": return .pink
        case "amber": return .orange
        case "red": return .red
        case "teal": return .teal
        case "gray": return .gray
        default: return appState.themeAccent   // matcha + unknown
        }
    }

    private func iconColor(_ name: String?, fallback: Color) -> Color {
        guard let name, !name.isEmpty else { return fallback }
        return paletteColor(name)
    }

    private func toggle(_ id: String) {
        if collapsed.contains(id) { collapsed.remove(id) } else { collapsed.insert(id) }
    }

    private func ensureModeFor(_ jid: String) {
        guard let j = journals.first(where: { $0.id == jid }) else { return }
        if let fid = j.folderId { mode = .folder(fid); collapsed.remove(fid) }
    }

    private func startFolderRename(_ folder: MWJournalFolder) {
        renamingJournalId = nil
        renameText = folder.name
        renamingFolderId = folder.id
        renameFocused = true
    }

    private func startNoteRename(_ j: MWJournal) {
        renamingFolderId = nil
        selectedJournalId = j.id
        renameText = j.title
        renamingJournalId = j.id
        renameFocused = true
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
            if case .folder(let id) = mode, !folders.contains(where: { $0.id == id }) { mode = .all }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func refreshNotes() async {
        if let j = try? await MatchaWorkService.shared.listJournals(forceRefresh: true) { journals = j }
    }

    private func newFolder(parent: String?) async {
        do {
            let f = try await MatchaWorkService.shared.createJournalFolder(name: "New Folder", parentId: parent)
            if let parent { collapsed.remove(parent) }
            await load()
            startFolderRename(f)
        } catch { errorMessage = error.localizedDescription }
    }

    private func deleteFolder(_ folder: MWJournalFolder) async {
        do {
            try await MatchaWorkService.shared.deleteJournalFolder(id: folder.id)
            if mode == .folder(folder.id) { mode = .all }
            appState.journalsListGeneration &+= 1
            await load()
        } catch { errorMessage = error.localizedDescription }
    }

    private func setFolderColor(_ folder: MWJournalFolder, _ color: String) async {
        _ = try? await MatchaWorkService.shared.updateJournalFolder(id: folder.id, color: color)
        await load()
    }

    private func commitFolderRename(_ id: String) async {
        let name = renameText.trimmingCharacters(in: .whitespaces)
        renamingFolderId = nil
        guard !name.isEmpty else { return }
        _ = try? await MatchaWorkService.shared.renameJournalFolder(id: id, name: name)
        await load()
    }

    private func createNote(_ kind: JournalKind) async {
        do {
            let j = try await MatchaWorkService.shared.createJournal(
                title: "", description: nil, color: nil, icon: nil,
                kind: kind.rawValue, folderId: currentFolderId,
            )
            appState.journalsListGeneration &+= 1
            await load()
            selectedJournalId = j.id
            startNoteRename(j)
        } catch { errorMessage = error.localizedDescription }
    }

    private func commitNoteRename(_ id: String) async {
        let name = renameText.trimmingCharacters(in: .whitespaces)
        renamingJournalId = nil
        guard !name.isEmpty else { return }
        _ = try? await MatchaWorkService.shared.updateJournal(
            id: id, title: name, description: nil, color: nil, icon: nil,
        )
        appState.journalsListGeneration &+= 1
        await refreshNotes()
    }

    private func setNoteColor(_ j: MWJournal, _ color: String) async {
        _ = try? await MatchaWorkService.shared.updateJournal(
            id: j.id, title: nil, description: nil, color: color, icon: nil,
        )
        await refreshNotes()
    }

    private func move(_ j: MWJournal, to folderId: String?) async {
        do {
            _ = try await MatchaWorkService.shared.moveJournal(id: j.id, folderId: folderId)
            if let folderId { collapsed.remove(folderId) }
            appState.journalsListGeneration &+= 1
            await load()
        } catch { errorMessage = error.localizedDescription }
    }

    private func archive(_ j: MWJournal) async {
        try? await JournalService.shared.archiveJournal(id: j.id)
        if selectedJournalId == j.id { selectedJournalId = nil }
        appState.journalsListGeneration &+= 1
        await load()
    }

    private func confirmDelete(_ j: MWJournal) {
        let alert = NSAlert()
        alert.messageText = "Delete \"\(j.title.isEmpty ? "Untitled" : j.title)\"?"
        alert.informativeText = "Permanently deletes the document and its contents. Cannot be undone."
        alert.alertStyle = .critical
        alert.addButton(withTitle: "Delete Permanently")
        alert.addButton(withTitle: "Cancel")
        guard alert.runModal() == .alertFirstButtonReturn else { return }
        Task {
            try? await JournalService.shared.deleteJournal(id: j.id)
            if selectedJournalId == j.id { selectedJournalId = nil }
            appState.journalsListGeneration &+= 1
            await load()
        }
    }
}
