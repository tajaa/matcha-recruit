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
                alert.informativeText = "Permanently deletes the journal and its contents. Cannot be undone."
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
        case .note: return "Journal"
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
    /// List / card tint for a journal with no color of its own, so the list
    /// reads by type at a glance. nil = neutral: plain journals, the bulk of
    /// the list, stay quiet instead of all taking the accent.
    var tint: Color? {
        switch self {
        case .blog: return .blue
        case .todo: return .teal
        case .novel: return .purple
        case .screenplay: return .pink
        case .note, .journal: return nil
        }
    }
    var blurb: String {
        switch self {
        case .note: return "A blank journal for quick thoughts."
        case .blog: return "Title, hook, sections, CTA."
        case .todo: return "Today / this week / someday checklist."
        case .novel: return "Chapter heading + scene break."
        case .screenplay: return "Sluglines, action, dialogue."
        case .journal: return "Plain dated entries."
        }
    }
    static func from(_ raw: String?) -> JournalKind { JournalKind(rawValue: raw ?? "note") ?? .note }

    // MARK: - Workspace behavior

    /// Every journal is a single-document workspace (Evernote model) — opens straight
    /// into one editor backed by a single body entry. The `.journal` (diary)
    /// kind is retained only to decode any pre-migration row; its old
    /// multi-entry timeline is gone, so this is always true.
    var isDocKind: Bool { true }

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
            return [.heading, .subheading, .image, .quote, .divider, .bullet, .numbered, .code, .math, .diagram, .link]
        case .novel:
            return [.chapter, .sceneBreak, .quote, .image]
        case .note:
            return [.heading, .bullet, .todo, .quote, .code, .math, .diagram, .image, .divider, .link]
        case .todo:
            return [.todo, .heading, .bullet, .divider]
        case .journal:
            return [.heading, .bullet, .todo, .quote, .code, .math, .diagram, .image, .divider]
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
    static let math       = SlashBlock(id: "math",       title: "Math (LaTeX)",   subtitle: "Display equation",    icon: "function",                               keywords: ["latex", "equation", "formula", "tex"], insert: .snippet("\n$$\n\n$$\n"))
    static let diagram    = SlashBlock(id: "diagram",    title: "Diagram (Mermaid)", subtitle: "Flowchart / graph", icon: "point.3.connected.trianglepath.dotted", keywords: ["mermaid", "graph", "chart", "flow"], insert: .snippet("\n```mermaid\ngraph TD\n  A[Start] --> B[End]\n```\n"))
}

// MARK: - Journals workspace (macOS Notes / Evernote, three columns)

/// The Journals surface: folder rail · journal list (title + snippet + modified
/// date) · document editor. Folders are colorable + nestable; journals are
/// color-coded by document type and open in the embedded per-kind editor
/// (markdown or screenplay). The col-3 selection is LOCAL — picking a journal must
/// not route the primary pane away from this workspace.
struct JournalsWorkspace: View {
    @Environment(AppState.self) private var appState

    enum FolderMode: Equatable { case all, starred, shared, uncategorized, folder(String) }
    enum SortKey: String, CaseIterable { case modified = "Date Modified", created = "Date Created", title = "Title" }

    @State private var folders: [MWJournalFolder] = []
    @State private var journals: [MWJournal] = []
    @State private var mode: FolderMode = .all
    @State private var collapsed: Set<String> = []
    @AppStorage("journals.listSort") private var sortRaw: String = SortKey.modified.rawValue
    @State private var search = ""
    @State private var selectedJournalId: String? = nil       // local col-3 selection
    @State private var renamingFolderId: String? = nil
    @State private var renamingJournalId: String? = nil
    @State private var renameText = ""
    @State private var hasLoaded = false
    @State private var errorMessage: String?
    @AppStorage("journals.folderRailCollapsed") private var folderRailCollapsed = false
    /// Rail row a dragged journal is hovering ("uncategorized" or a folder id).
    @State private var dropTarget: String? = nil
    @State private var scrollTarget: String? = nil
    @FocusState private var renameFocused: Bool
    @FocusState private var listFocused: Bool

    private let palette = ["matcha", "blue", "purple", "pink", "amber", "red", "teal", "gray"]
    /// Diary `.journal` kind is retired — every new journal is a single
    /// document. Only the doc-kind templates are offered.
    private static let creatableKinds = JournalKind.allCases.filter { $0 != .journal }
    /// Drag payload prefix, so a journal dropped on a folder can't be confused
    /// with plain text dragged in from elsewhere.
    private static let dragPrefix = "espresso-journal:"

    private var sort: SortKey { SortKey(rawValue: sortRaw) ?? .modified }

    var body: some View {
        HSplitView {
            if folderRailCollapsed {
                MWHubRailStrip { folderRailCollapsed = false }
            } else {
                folderRail.frame(minWidth: 190, idealWidth: 220, maxWidth: 280)
            }
            noteList.frame(minWidth: 260, idealWidth: 310, maxWidth: 400)
            editorPane.frame(minWidth: 380, maxWidth: .infinity, maxHeight: .infinity)
        }
        .background(ThemeRadialBackground())
        .foldsRailForSidePane($folderRailCollapsed)
        // ⌘N anywhere in the workspace — the list header's compose button is
        // a menu, which can't carry a shortcut of its own.
        .background {
            Button("New journal") { Task { await createNote(.note) } }
                .keyboardShortcut("n", modifiers: .command)
                .opacity(0)
                .frame(width: 0, height: 0)
                .accessibilityHidden(true)
        }
        .task {
            await load()
            if let jid = appState.selectedJournalId { selectedJournalId = jid; ensureModeFor(jid) }
        }
        .onChange(of: appState.journalsListGeneration) { _, _ in Task { await load() } }
        .onChange(of: appState.selectedJournalId) { _, v in
            if let v { selectedJournalId = v; ensureModeFor(v) }
        }
        .onChange(of: selectedJournalId) { _, _ in
            // After leaving an edited journal, re-sort the list by recent edit
            // (the backend bumps the journal's updated_at on entry save).
            Task { try? await Task.sleep(for: .milliseconds(700)); await refreshNotes() }
        }
    }

    // ── Folder rail ─────────────────────────────────────────────────────

    private var folderRail: some View {
        let counts = railCounts
        return VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 10) {
                Text("Journals")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundColor(appState.themeTextSecondary)
                Spacer()
                MWHubRailIconButton(icon: "sidebar.left", help: "Hide folders") { folderRailCollapsed = true }
            }
            .padding(.horizontal, 14).padding(.top, 14).padding(.bottom, 8)

            ScrollView {
                LazyVStack(alignment: .leading, spacing: 1) {
                    smartRow(.all, title: "All Journals", icon: "tray.full", count: counts.all)
                    smartRow(.starred, title: "Starred", icon: "star", count: counts.starred)
                    if hasSharedNotes {
                        smartRow(.shared, title: "Shared with me", icon: "person.2", count: counts.shared)
                    }
                    smartRow(.uncategorized, title: "Uncategorized", icon: "tray", count: counts.uncategorized)
                        .dropDestination(for: String.self) { items, _ in
                            handleDrop(items, into: nil)
                        } isTargeted: { setDropTarget("uncategorized", $0) }

                    foldersHeading

                    if folders.isEmpty {
                        Button { Task { await newFolder(parent: nil) } } label: {
                            JournalRailRow(icon: "folder.badge.plus",
                                           iconColor: appState.themeSidebarTextSecondary,
                                           selected: false) {
                                Text("New folder")
                                    .font(.system(size: 12))
                                    .foregroundColor(appState.themeSidebarTextSecondary)
                            }
                        }
                        .buttonStyle(.plain)
                    } else {
                        ForEach(visibleFolders, id: \.0.id) { pair in
                            folderTreeRow(pair.0, depth: pair.1, count: counts.folders[pair.0.id] ?? 0)
                        }
                    }
                }
                .padding(.horizontal, 8).padding(.bottom, 12)
            }
        }
        .frame(maxHeight: .infinity, alignment: .top)
        .background(appState.themeSidebar)
    }

    private var foldersHeading: some View {
        HStack(spacing: 4) {
            Text("FOLDERS")
                .font(.system(size: 9, weight: .semibold))
                .tracking(0.6)
                .foregroundColor(appState.themeSidebarTextSecondary)
            Spacer()
            Button { Task { await newFolder(parent: nil) } } label: {
                Image(systemName: "plus")
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundColor(appState.themeSidebarTextSecondary)
                    .frame(width: 18, height: 18)
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .help("New folder")
        }
        .padding(.leading, 8).padding(.trailing, 4).padding(.top, 14).padding(.bottom, 3)
    }

    private func smartRow(_ target: FolderMode, title: String, icon: String, count: Int) -> some View {
        let selected = mode == target
        let isDrop = target == .uncategorized && dropTarget == "uncategorized"
        return Button { mode = target } label: {
            JournalRailRow(icon: icon,
                           iconColor: selected ? appState.themeSidebarAccent : appState.themeSidebarTextSecondary,
                           selected: selected, count: count, isDropTarget: isDrop) {
                Text(title)
                    .font(.system(size: 12, weight: selected ? .semibold : .regular))
                    .foregroundColor(appState.themeSidebarText.opacity(0.92))
                    .lineLimit(1)
            }
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

    /// A folder row. Renaming swaps only the title for a field — the row frame,
    /// gutter and icon stay put, so nothing jumps while you type.
    @ViewBuilder
    private func folderTreeRow(_ folder: MWJournalFolder, depth: Int, count: Int) -> some View {
        let isSel = mode == .folder(folder.id)
        let tint = iconColor(folder.color, fallback: isSel ? appState.themeSidebarAccent : appState.themeSidebarTextSecondary)
        let expandable = hasChildren(folder.id)
        let isOpen = !collapsed.contains(folder.id)

        Group {
            if renamingFolderId == folder.id {
                JournalRailRow(depth: depth, icon: "folder.fill", iconColor: tint, selected: true, count: count) {
                    renameField("Folder name", size: 12, weight: .regular, color: appState.themeSidebarText) {
                        commitFolderRename(folder.id)
                    }
                }
            } else {
                Button { mode = .folder(folder.id) } label: {
                    JournalRailRow(depth: depth, icon: "folder.fill", iconColor: tint, selected: isSel,
                                   count: count, isDropTarget: dropTarget == folder.id) {
                        Text(folder.name)
                            .font(.system(size: 12, weight: isSel ? .semibold : .regular))
                            .foregroundColor(appState.themeSidebarText.opacity(0.92))
                            .lineLimit(1)
                    }
                }
                .buttonStyle(.plain)
                .simultaneousGesture(TapGesture(count: 2).onEnded { startFolderRename(folder) })
                .dropDestination(for: String.self) { items, _ in
                    handleDrop(items, into: folder.id)
                } isTargeted: { setDropTarget(folder.id, $0) }
                .contextMenu {
                    Button("New journal here") { mode = .folder(folder.id); Task { await createNote(.note) } }
                    Button("New subfolder") { Task { await newFolder(parent: folder.id) } }
                    Divider()
                    Button("Rename…") { startFolderRename(folder) }
                    colorMenu { c in Task { await setFolderColor(folder, c) } }
                    Divider()
                    Button("Delete folder", role: .destructive) { Task { await deleteFolder(folder) } }
                }
            }
        }
        // The disclosure lives in the row's reserved gutter, outside the
        // select button so a click on it only expands/collapses.
        .overlay(alignment: .leading) {
            if expandable {
                Button { toggle(folder.id) } label: {
                    Image(systemName: "chevron.right")
                        .font(.system(size: 8, weight: .bold))
                        .rotationEffect(.degrees(isOpen ? 90 : 0))
                        .foregroundColor(appState.themeSidebarTextSecondary)
                        .frame(width: JournalRailRow<EmptyView>.gutter, height: 22)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .padding(.leading, JournalRailRow<EmptyView>.leadingInset(depth: depth))
                .help(isOpen ? "Collapse" : "Expand")
            }
        }
    }

    // ── Note list (col 2) ───────────────────────────────────────────────

    private var noteList: some View {
        VStack(spacing: 0) {
            listHeader
            Divider().opacity(0.2)

            if !hasLoaded && errorMessage == nil {
                Spacer()
                ProgressView().controlSize(.small)
                Spacer()
            } else if !hasLoaded, let errorMessage {
                loadErrorState(errorMessage)
            } else if shownNotes.isEmpty {
                noteEmptyState
            } else {
                ScrollViewReader { proxy in
                    ScrollView {
                        LazyVStack(alignment: .leading, spacing: 2) {
                            ForEach(sections) { section in
                                if let title = section.title { sectionHeader(title) }
                                ForEach(section.notes) { j in
                                    noteRowContainer(j).id(j.id)
                                }
                            }
                        }
                        .padding(.vertical, 6).padding(.horizontal, 8)
                    }
                    .onChange(of: scrollTarget) { _, id in
                        guard let id else { return }
                        proxy.scrollTo(id)
                    }
                }
                .focusable()
                .focused($listFocused)
                .focusEffectDisabled()
                .onKeyPress(.upArrow) { step(-1); return .handled }
                .onKeyPress(.downArrow) { step(1); return .handled }
            }

            if hasLoaded, let errorMessage { errorBanner(errorMessage) }
        }
        .frame(maxHeight: .infinity, alignment: .top)
        .background(appState.themeBg.opacity(0.3))
    }

    private var listHeader: some View {
        VStack(spacing: 10) {
            HStack(spacing: 6) {
                Text(listTitle)
                    .font(.system(size: 13, weight: .bold))
                    .foregroundColor(appState.themeText)
                    .lineLimit(1)
                Text(countLabel)
                    .font(.system(size: 11))
                    .monospacedDigit()
                    .foregroundColor(appState.themeTextSecondary)
                    .lineLimit(1)
                Spacer(minLength: 4)
                Menu {
                    Picker("Sort by", selection: $sortRaw) {
                        ForEach(SortKey.allCases, id: \.self) { s in Text(s.rawValue).tag(s.rawValue) }
                    }
                    .pickerStyle(.inline)
                } label: {
                    Image(systemName: "arrow.up.arrow.down").font(.system(size: 11, weight: .medium))
                }
                .menuStyle(.borderlessButton)
                .menuIndicator(.hidden)
                .fixedSize()
                // Borderless menu labels take the window tint, not
                // foregroundColor — keep sort neutral; compose is the one accent.
                .tint(appState.themeTextSecondary)
                .help("Sort: \(sort.rawValue)")
                Menu {
                    ForEach(Self.creatableKinds) { k in
                        Button { Task { await createNote(k) } } label: { Label(k.label, systemImage: k.icon) }
                    }
                } label: {
                    Image(systemName: "square.and.pencil").font(.system(size: 13, weight: .medium))
                } primaryAction: {
                    Task { await createNote(.note) }
                }
                .menuStyle(.borderlessButton)
                .menuIndicator(.visible)
                .fixedSize()
                .tint(appState.themeAccent)
                .help("New journal (⌘N) · arrow for templates")
            }

            HStack(spacing: 6) {
                Image(systemName: "magnifyingglass")
                    .font(.system(size: 11))
                    .foregroundColor(appState.themeTextSecondary)
                TextField("Search \(listTitle)", text: $search)
                    .textFieldStyle(.plain)
                    .font(.system(size: 12))
                    .foregroundColor(appState.themeText)
                if !search.isEmpty {
                    Button { search = "" } label: {
                        Image(systemName: "xmark.circle.fill").font(.system(size: 11))
                    }
                    .buttonStyle(.plain)
                    .foregroundColor(appState.themeTextSecondary)
                    .help("Clear search")
                }
            }
            .padding(.horizontal, 8).padding(.vertical, 5)
            .background(RoundedRectangle(cornerRadius: 6).fill(appState.themeCard.opacity(0.6)))
            .overlay(RoundedRectangle(cornerRadius: 6).strokeBorder(appState.themeBorder.opacity(0.35), lineWidth: 0.5))
        }
        .padding(.horizontal, 12).padding(.top, 14).padding(.bottom, 10)
    }

    private func sectionHeader(_ title: String) -> some View {
        Text(title.uppercased())
            .font(.system(size: 9.5, weight: .semibold))
            .tracking(0.6)
            .foregroundColor(appState.themeTextSecondary)
            .padding(.horizontal, 10).padding(.top, 10).padding(.bottom, 3)
    }

    /// Own journals drag onto a folder (or Uncategorized) to file them. A
    /// journal shared with me sits in its owner's tree, so it can't be moved.
    @ViewBuilder
    private func noteRowContainer(_ j: MWJournal) -> some View {
        if j.isSharedWithMe || renamingJournalId == j.id {
            noteRow(j)
        } else {
            noteRow(j).draggable(Self.dragPrefix + j.id) {
                Label(displayTitle(j), systemImage: j.icon ?? JournalKind.from(j.kind).icon)
                    .font(.system(size: 12, weight: .medium))
                    .padding(.horizontal, 10).padding(.vertical, 6)
                    .background(RoundedRectangle(cornerRadius: 6).fill(appState.themeCard))
            }
        }
    }

    @ViewBuilder
    private func noteRow(_ j: MWJournal) -> some View {
        let _ = JournalStarStore.shared.generation
        let kind = JournalKind.from(j.kind)
        let selected = selectedJournalId == j.id
        let row: (AnyView) -> JournalNoteRow<AnyView> = { title in
            JournalNoteRow(
                icon: j.icon ?? kind.icon,
                tint: noteTint(j),
                selected: selected,
                dateLabel: rowDate(j),
                preview: j.preview,
                starred: JournalStarStore.shared.isStarred(j.id),
                folderName: showsFolderNames ? folderName(j.folderId) : nil,
                sharedBy: j.isSharedWithMe ? (j.ownerName.map { "Shared by \($0)" } ?? "Shared") : nil,
            ) { title }
        }
        if renamingJournalId == j.id {
            row(AnyView(renameField("Title", size: 13, weight: .semibold, color: appState.themeText) {
                commitNoteRename(j.id)
            }))
        } else {
            Button {
                selectedJournalId = j.id
                listFocused = true
            } label: {
                row(AnyView(
                    Text(displayTitle(j))
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundColor(appState.themeText)
                        .lineLimit(1)
                ))
            }
            .buttonStyle(.plain)
            .simultaneousGesture(TapGesture(count: 2).onEnded { startNoteRename(j) })
            .contextMenu { noteMenu(j) }
        }
    }

    @ViewBuilder
    private func noteMenu(_ j: MWJournal) -> some View {
        Button("Rename") { startNoteRename(j) }
        colorMenu { c in Task { await setNoteColor(j, c) } }
        if !j.isSharedWithMe {
            Menu("Move to") {
                Button("Uncategorized") { Task { await move(j, to: nil) } }
                    .disabled(j.folderId == nil)
                if !folders.isEmpty { Divider() }
                ForEach(folders.sorted { $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending }) { f in
                    Button(f.name) { Task { await move(j, to: f.id) } }
                        .disabled(j.folderId == f.id)
                }
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

    /// Inline rename field. Sits on a faint well that bleeds 4pt past the
    /// text on each side, so the typed text lines up with the static title.
    private func renameField(
        _ placeholder: String, size: CGFloat, weight: Font.Weight, color: Color,
        onCommit: @escaping () -> Void
    ) -> some View {
        TextField(placeholder, text: $renameText)
            .textFieldStyle(.plain)
            .font(.system(size: size, weight: weight))
            .foregroundColor(color)
            .focused($renameFocused)
            .onAppear { DispatchQueue.main.async { renameFocused = true } }
            .onSubmit(onCommit)
            .onExitCommand { cancelRename() }
            .onChange(of: renameFocused) { _, focused in if !focused { onCommit() } }
            .padding(.horizontal, 4).padding(.vertical, 1)
            .background(RoundedRectangle(cornerRadius: 4).fill(appState.themeBg.opacity(0.55)))
            .overlay(RoundedRectangle(cornerRadius: 4).strokeBorder(appState.themeAccent.opacity(0.55), lineWidth: 1))
            .padding(.horizontal, -4)
    }

    // ── Empty / error states ────────────────────────────────────────────

    private var noteEmptyState: some View {
        let copy = emptyCopy
        return VStack(spacing: 10) {
            Spacer()
            Image(systemName: copy.icon)
                .font(.system(size: 20, weight: .light))
                .foregroundColor(appState.themeTextSecondary)
                .frame(width: 48, height: 48)
                .background(Circle().fill(appState.themeText.opacity(0.05)))
            Text(copy.title)
                .font(.system(size: 13, weight: .semibold))
                .foregroundColor(appState.themeText)
                .multilineTextAlignment(.center)
            Text(copy.detail)
                .font(.system(size: 11.5))
                .foregroundColor(appState.themeTextSecondary)
                .multilineTextAlignment(.center)
                .frame(maxWidth: 230)
            if !search.isEmpty {
                Button("Clear search") { search = "" }
                    .controlSize(.small)
                    .padding(.top, 2)
            } else if copy.canCreate {
                Button { Task { await createNote(.note) } } label: {
                    Label("New journal", systemImage: "square.and.pencil")
                        .font(.system(size: 11.5, weight: .medium))
                }
                .buttonStyle(.borderedProminent)
                .tint(appState.themeAccent)
                .controlSize(.small)
                .padding(.top, 2)
            }
            Spacer()
            Spacer()
        }
        .padding(.horizontal, 20)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private var emptyCopy: (icon: String, title: String, detail: String, canCreate: Bool) {
        if !search.isEmpty {
            return ("magnifyingglass", "No matches for “\(search)”", "Try a different word, or search another folder.", false)
        }
        switch mode {
        case .all:
            return ("book.closed", "No journals yet", "Capture notes, drafts and to-dos. Press ⌘N to start one.", true)
        case .starred:
            return ("star", "Nothing starred", "Star a journal from its right-click menu to keep it here.", false)
        case .shared:
            return ("person.2", "Nothing shared with you", "Journals a collaborator invites you to will show up here.", false)
        case .uncategorized:
            return ("tray", "No unfiled journals", "Journals that aren't in a folder land here.", true)
        case .folder:
            return ("folder", "This folder is empty", "Start a journal here, or drag one in from the list.", true)
        }
    }

    private func loadErrorState(_ message: String) -> some View {
        VStack(spacing: 10) {
            Spacer()
            Image(systemName: "exclamationmark.triangle")
                .font(.system(size: 20, weight: .light))
                .foregroundColor(.orange)
            Text("Couldn't load journals")
                .font(.system(size: 13, weight: .semibold))
                .foregroundColor(appState.themeText)
            Text(message)
                .font(.system(size: 11))
                .foregroundColor(appState.themeTextSecondary)
                .multilineTextAlignment(.center)
                .lineLimit(3)
                .frame(maxWidth: 240)
            Button("Try again") { Task { await load() } }
                .controlSize(.small)
            Spacer()
            Spacer()
        }
        .padding(.horizontal, 20)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private func errorBanner(_ message: String) -> some View {
        HStack(spacing: 5) {
            Image(systemName: "exclamationmark.triangle.fill").font(.system(size: 9))
            Text(message).font(.system(size: 10.5)).lineLimit(2)
            Spacer(minLength: 0)
            Button { errorMessage = nil } label: {
                Image(systemName: "xmark").font(.system(size: 8, weight: .semibold))
            }
            .buttonStyle(.plain)
            .help("Dismiss")
        }
        .foregroundColor(.orange)
        .padding(.horizontal, 12).padding(.vertical, 6)
    }

    // ── Editor (col 3) ──────────────────────────────────────────────────

    @ViewBuilder
    private var editorPane: some View {
        if let jid = selectedJournalId {
            JournalDetailView(journalId: jid, isEmbedded: true)
        } else {
            JournalsStartPane(
                kinds: Self.creatableKinds,
                destination: newJournalDestination,
                tint: { kindTint($0) },
            ) { kind in Task { await createNote(kind) } }
        }
    }

    // ── Derived ─────────────────────────────────────────────────────────

    private var listTitle: String {
        switch mode {
        case .all: return "All Journals"
        case .starred: return "Starred"
        case .shared: return "Shared with me"
        case .uncategorized: return "Uncategorized"
        case .folder(let id): return folders.first { $0.id == id }?.name ?? "Folder"
        }
    }

    private var countLabel: String {
        let n = shownNotes.count
        return search.isEmpty ? "\(n)" : "\(n) found"
    }

    /// Where ⌘N / a template card files the new journal, for the start pane's
    /// hint. Starred and Shared views create at the root.
    private var newJournalDestination: String? {
        switch mode {
        case .folder, .uncategorized: return listTitle
        default: return nil
        }
    }

    /// Any journals shared with me (I'm a collaborator, not the owner)?
    private var hasSharedNotes: Bool { journals.contains { $0.isSharedWithMe } }

    private var currentFolderId: String? {
        if case .folder(let id) = mode { return id }
        return nil
    }

    /// Cross-folder views say where each journal is filed.
    private var showsFolderNames: Bool { mode == .all || mode == .starred }

    private struct RailCounts {
        var all = 0, starred = 0, shared = 0, uncategorized = 0
        var folders: [String: Int] = [:]
    }

    /// Per-row counts, matching what each view lists (`shownNotes`).
    private var railCounts: RailCounts {
        _ = JournalStarStore.shared.generation
        var c = RailCounts()
        for j in journals {
            if JournalStarStore.shared.isStarred(j.id) { c.starred += 1 }
            if j.isSharedWithMe { c.shared += 1; continue }
            c.all += 1
            if let f = j.folderId { c.folders[f, default: 0] += 1 } else { c.uncategorized += 1 }
        }
        return c
    }

    private var shownNotes: [MWJournal] {
        _ = JournalStarStore.shared.generation
        var base: [MWJournal]
        switch mode {
        // "All Journals" + folders are PERSONAL (my own). Journals shared with me by
        // a collaborator live only under "Shared with me" so they don't blend
        // into my own notebooks.
        case .all: base = journals.filter { !$0.isSharedWithMe }
        case .starred: base = journals.filter { JournalStarStore.shared.isStarred($0.id) }
        case .shared: base = journals.filter { $0.isSharedWithMe }
        case .uncategorized: base = journals.filter { $0.folderId == nil && !$0.isSharedWithMe }
        case .folder(let id): base = journals.filter { $0.folderId == id && !$0.isSharedWithMe }
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

    private struct NoteSection: Identifiable {
        let id: String
        let title: String?
        let notes: [MWJournal]
    }

    /// Date-sorted lists group like Notes (Today · Yesterday · Previous 7 Days
    /// · Previous 30 Days · month · year), in Pacific like every other date in
    /// the app. A title sort is one ungrouped run.
    private var sections: [NoteSection] {
        let notes = shownNotes
        guard sort != .title, !notes.isEmpty else { return [NoteSection(id: "all", title: nil, notes: notes)] }
        let cal = PacificDateFormatter.pacificCalendar
        let startOfToday = cal.startOfDay(for: Date())
        var order: [String] = []
        var buckets: [String: [MWJournal]] = [:]
        for j in notes {
            let key = Self.bucketTitle(for: sortDate(j), calendar: cal, startOfToday: startOfToday)
            if buckets[key] == nil { order.append(key) }
            buckets[key, default: []].append(j)
        }
        return order.map { NoteSection(id: $0, title: $0, notes: buckets[$0] ?? []) }
    }

    private func sortDate(_ j: MWJournal) -> Date? {
        PacificDateFormatter.parse(sort == .created ? j.createdAt : j.updatedAt)
    }

    private static let monthFmt = PacificDateFormatter.display { $0.dateFormat = "LLLL" }
    private static let yearFmt = PacificDateFormatter.display { $0.dateFormat = "yyyy" }
    private static let weekdayFmt = PacificDateFormatter.display { $0.dateFormat = "EEEE" }
    private static let timeFmt = PacificDateFormatter.display { $0.dateFormat = "h:mm a" }
    private static let dayFmt = PacificDateFormatter.display { $0.dateFormat = "MMM d" }
    private static let fullDayFmt = PacificDateFormatter.display { $0.dateFormat = "M/d/yy" }

    private static func bucketTitle(for date: Date?, calendar cal: Calendar, startOfToday: Date) -> String {
        guard let date else { return "Earlier" }
        func daysAgo(_ n: Int) -> Date { cal.date(byAdding: .day, value: -n, to: startOfToday) ?? startOfToday }
        if date >= startOfToday { return "Today" }
        if date >= daysAgo(1) { return "Yesterday" }
        if date >= daysAgo(7) { return "Previous 7 Days" }
        if date >= daysAgo(30) { return "Previous 30 Days" }
        if cal.isDate(date, equalTo: startOfToday, toGranularity: .year) { return monthFmt.string(from: date) }
        return yearFmt.string(from: date)
    }

    /// Notes-style row date: a time today, "Yesterday", a weekday this week,
    /// then a short date.
    private func rowDate(_ j: MWJournal) -> String {
        guard let d = sortDate(j) else { return "" }
        let cal = PacificDateFormatter.pacificCalendar
        let startOfToday = cal.startOfDay(for: Date())
        if d >= startOfToday { return Self.timeFmt.string(from: d) }
        if let y = cal.date(byAdding: .day, value: -1, to: startOfToday), d >= y { return "Yesterday" }
        if let w = cal.date(byAdding: .day, value: -6, to: startOfToday), d >= w { return Self.weekdayFmt.string(from: d) }
        if cal.isDate(d, equalTo: startOfToday, toGranularity: .year) { return Self.dayFmt.string(from: d) }
        return Self.fullDayFmt.string(from: d)
    }

    private func displayTitle(_ j: MWJournal) -> String { j.title.isEmpty ? "Untitled" : j.title }

    private func folderName(_ id: String?) -> String? {
        guard let id else { return nil }
        return folders.first { $0.id == id }?.name
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

    private func kindTint(_ kind: JournalKind) -> Color { kind.tint ?? appState.themeTextSecondary }

    /// A journal's own color wins; otherwise it's color-coded by type.
    private func noteTint(_ j: MWJournal) -> Color {
        iconColor(j.color, fallback: kindTint(JournalKind.from(j.kind)))
    }

    private func toggle(_ id: String) {
        if collapsed.contains(id) { collapsed.remove(id) } else { collapsed.insert(id) }
    }

    private func ensureModeFor(_ jid: String) {
        guard let j = journals.first(where: { $0.id == jid }) else { return }
        // A journal shared with me carries the OWNER's folder_id (not in my tree),
        // so route it to the "Shared with me" view, not a phantom folder.
        if j.isSharedWithMe { mode = .shared; return }
        if let fid = j.folderId { mode = .folder(fid); collapsed.remove(fid) } else { mode = .uncategorized }
    }

    /// Arrow-key selection through the list, in display order.
    private func step(_ delta: Int) {
        let ids = sections.flatMap { $0.notes.map(\.id) }
        guard !ids.isEmpty else { return }
        let current = selectedJournalId.flatMap { ids.firstIndex(of: $0) } ?? (delta > 0 ? -1 : ids.count)
        let next = min(max(current + delta, 0), ids.count - 1)
        selectedJournalId = ids[next]
        scrollTarget = ids[next]
    }

    private func setDropTarget(_ key: String, _ targeted: Bool) {
        if targeted { dropTarget = key } else if dropTarget == key { dropTarget = nil }
    }

    private func handleDrop(_ items: [String], into folderId: String?) -> Bool {
        let ids = Set(items.compactMap { item -> String? in
            item.hasPrefix(Self.dragPrefix) ? String(item.dropFirst(Self.dragPrefix.count)) : nil
        })
        let moving = journals.filter { ids.contains($0.id) && !$0.isSharedWithMe && $0.folderId != folderId }
        dropTarget = nil
        guard !moving.isEmpty else { return false }
        Task { for j in moving { await move(j, to: folderId) } }
        return true
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

    /// Escape: drop the edit. Clearing the ids first makes the focus-loss
    /// commit that follows a no-op.
    private func cancelRename() {
        renamingFolderId = nil
        renamingJournalId = nil
    }

    // ── Data ────────────────────────────────────────────────────────────

    private func load() async {
        do {
            async let f = MatchaWorkService.shared.listJournalFolders()
            async let j = MatchaWorkService.shared.listJournals(forceRefresh: true)
            folders = try await f
            journals = try await j
            errorMessage = nil
            hasLoaded = true
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

    /// Ends the edit synchronously (so Return and the focus loss that follows
    /// don't both save), then renames in the background.
    private func commitFolderRename(_ id: String) {
        guard renamingFolderId == id else { return }
        let name = renameText.trimmingCharacters(in: .whitespacesAndNewlines)
        renamingFolderId = nil
        guard !name.isEmpty, name != folders.first(where: { $0.id == id })?.name else { return }
        Task {
            _ = try? await MatchaWorkService.shared.renameJournalFolder(id: id, name: name)
            await load()
        }
    }

    private func createNote(_ kind: JournalKind) async {
        do {
            let j = try await MatchaWorkService.shared.createJournal(
                title: "", description: nil, color: nil, icon: nil,
                kind: kind.rawValue, folderId: currentFolderId,
                explicitlyUnfiled: mode == .uncategorized,
            )
            appState.journalsListGeneration &+= 1
            await load()
            // Starred / Shared views can't show a brand-new journal; jump to
            // where it was filed so the rename field is on screen.
            if mode == .starred || mode == .shared { mode = .all }
            search = ""
            selectedJournalId = j.id
            startNoteRename(j)
        } catch { errorMessage = error.localizedDescription }
    }

    private func commitNoteRename(_ id: String) {
        guard renamingJournalId == id else { return }
        let name = renameText.trimmingCharacters(in: .whitespacesAndNewlines)
        renamingJournalId = nil
        guard !name.isEmpty, name != journals.first(where: { $0.id == id })?.title else { return }
        Task {
            _ = try? await MatchaWorkService.shared.updateJournal(
                id: id, title: name, description: nil, color: nil, icon: nil,
            )
            appState.journalsListGeneration &+= 1
            await refreshNotes()
        }
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
        alert.messageText = "Delete \"\(displayTitle(j))\"?"
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

// MARK: - Workspace pieces

/// One row in the Journals folder rail. Every row — smart folder, user folder,
/// a folder being renamed — shares this frame (disclosure gutter · icon ·
/// title · count), so icons and titles line up the whole way down. Nesting
/// shifts the whole row right by `depth`; the caller draws the disclosure
/// chevron into the gutter.
struct JournalRailRow<Title: View>: View {
    static var gutter: CGFloat { 12 }
    static func leadingInset(depth: Int) -> CGFloat { 2 + CGFloat(depth) * 14 }

    var depth: Int = 0
    let icon: String
    let iconColor: Color
    let selected: Bool
    var count: Int? = nil
    var isDropTarget: Bool = false
    @ViewBuilder var title: () -> Title

    @Environment(AppState.self) private var appState
    @State private var hovering = false

    var body: some View {
        HStack(spacing: 0) {
            Color.clear.frame(width: Self.gutter, height: 1)
            Image(systemName: icon)
                .font(.system(size: 11))
                .foregroundColor(iconColor)
                .frame(width: 16)
                .padding(.trailing, 7)
            title()
            Spacer(minLength: 6)
            if let count, count > 0 {
                Text("\(count)")
                    .font(.system(size: 10.5))
                    .monospacedDigit()
                    .foregroundColor(appState.themeSidebarTextSecondary)
            }
        }
        .padding(.leading, Self.leadingInset(depth: depth))
        .padding(.trailing, 8)
        .frame(height: 26)
        .background(RoundedRectangle(cornerRadius: 6).fill(background))
        .overlay(
            RoundedRectangle(cornerRadius: 6)
                .strokeBorder(appState.themeSidebarAccent.opacity(isDropTarget ? 0.75 : 0), lineWidth: 1.5)
        )
        .contentShape(Rectangle())
        .onHover { hovering = $0 }
    }

    private var background: Color {
        if isDropTarget { return appState.themeSidebarAccent.opacity(0.16) }
        if selected { return appState.themeSidebarAccent.opacity(0.11) }
        if hovering { return appState.themeSidebarText.opacity(0.05) }
        return .clear
    }
}

/// One journal in the list: a type-tinted tile, the title with its date, a
/// two-line preview, and a meta line (star · folder · shared-by) when there is
/// something to say.
struct JournalNoteRow<Title: View>: View {
    let icon: String
    let tint: Color
    let selected: Bool
    let dateLabel: String
    let preview: String?
    var starred: Bool = false
    var folderName: String? = nil
    var sharedBy: String? = nil
    @ViewBuilder var title: () -> Title

    @Environment(AppState.self) private var appState
    @State private var hovering = false

    /// The snippet as one flowing line: a checklist or multi-paragraph body
    /// would otherwise spend both preview lines on its first item.
    private var previewText: String? {
        let p = (preview ?? "").split(whereSeparator: \.isWhitespace).joined(separator: " ")
        return p.isEmpty ? nil : p
    }

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            RoundedRectangle(cornerRadius: 7)
                .fill(tint.opacity(selected ? 0.24 : 0.14))
                .frame(width: 28, height: 28)
                .overlay(
                    Image(systemName: icon)
                        .font(.system(size: 12, weight: .medium))
                        .foregroundColor(tint)
                )
            VStack(alignment: .leading, spacing: 3) {
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    title()
                    Spacer(minLength: 4)
                    Text(dateLabel)
                        .font(.system(size: 10.5))
                        .monospacedDigit()
                        .foregroundColor(appState.themeTextSecondary)
                        .lineLimit(1)
                        .fixedSize()
                }
                Text(previewText ?? "No additional text")
                    .font(.system(size: 11.5))
                    .foregroundColor(appState.themeTextSecondary.opacity(previewText == nil ? 0.6 : 1))
                    .lineLimit(2)
                    .multilineTextAlignment(.leading)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, alignment: .leading)
                if starred || folderName != nil || sharedBy != nil {
                    metaLine.padding(.top, 1)
                }
            }
        }
        .padding(.horizontal, 10).padding(.vertical, 9)
        .background(RoundedRectangle(cornerRadius: 8).fill(background))
        .contentShape(Rectangle())
        .onHover { hovering = $0 }
    }

    private var metaLine: some View {
        HStack(spacing: 8) {
            if starred {
                Image(systemName: "star.fill")
                    .font(.system(size: 9))
                    .foregroundColor(appState.themeAccent)
            }
            if let folderName {
                Label(folderName, systemImage: "folder")
                    .labelStyle(JournalMetaLabelStyle())
                    .foregroundColor(appState.themeTextSecondary)
            }
            if let sharedBy {
                Label(sharedBy, systemImage: "person.2.fill")
                    .labelStyle(JournalMetaLabelStyle())
                    .foregroundColor(appState.themeTextSecondary)
                    .padding(.horizontal, 6).padding(.vertical, 2)
                    .background(Capsule().fill(appState.themeText.opacity(0.06)))
            }
        }
    }

    private var background: Color {
        if selected { return appState.themeAccent.opacity(0.16) }
        if hovering { return appState.themeText.opacity(0.045) }
        return .clear
    }
}

private struct JournalMetaLabelStyle: LabelStyle {
    func makeBody(configuration: Configuration) -> some View {
        HStack(spacing: 3) {
            configuration.icon.font(.system(size: 8.5))
            configuration.title.font(.system(size: 10, weight: .medium)).lineLimit(1)
        }
    }
}

/// Column 3 with nothing open: a short prompt and one card per journal type,
/// so the empty pane is the fastest way to start writing.
struct JournalsStartPane: View {
    let kinds: [JournalKind]
    /// Folder the new journal will land in (nil = top level).
    let destination: String?
    let tint: (JournalKind) -> Color
    let onCreate: (JournalKind) -> Void

    @Environment(AppState.self) private var appState

    var body: some View {
        VStack(spacing: 22) {
            VStack(spacing: 8) {
                Image(systemName: "book.closed")
                    .font(.system(size: 22, weight: .light))
                    .foregroundColor(appState.themeTextSecondary)
                    .frame(width: 52, height: 52)
                    .background(Circle().fill(appState.themeText.opacity(0.05)))
                Text("No journal open")
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundColor(appState.themeText)
                Text("Pick one from the list, or start something new.")
                    .font(.system(size: 12))
                    .foregroundColor(appState.themeTextSecondary)
            }

            LazyVGrid(columns: [GridItem(.adaptive(minimum: 150, maximum: 200), spacing: 10)], spacing: 10) {
                ForEach(kinds) { kind in
                    JournalKindCard(kind: kind, tint: tint(kind)) { onCreate(kind) }
                }
            }
            .frame(maxWidth: 560)

            HStack(spacing: 6) {
                Text("⌘N")
                    .font(.system(size: 10.5, weight: .semibold, design: .rounded))
                    .foregroundColor(appState.themeTextSecondary)
                    .padding(.horizontal, 5).padding(.vertical, 2)
                    .background(RoundedRectangle(cornerRadius: 4).strokeBorder(appState.themeBorder.opacity(0.8), lineWidth: 1))
                Text(destination.map { "New journal in \($0)" } ?? "New journal")
                    .font(.system(size: 11))
                    .foregroundColor(appState.themeTextSecondary)
                    .lineLimit(1)
            }
        }
        .padding(32)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color.appBackground)
    }
}

private struct JournalKindCard: View {
    let kind: JournalKind
    let tint: Color
    let action: () -> Void

    @Environment(AppState.self) private var appState
    @State private var hovering = false

    var body: some View {
        Button(action: action) {
            VStack(alignment: .leading, spacing: 7) {
                RoundedRectangle(cornerRadius: 7)
                    .fill(tint.opacity(0.14))
                    .frame(width: 28, height: 28)
                    .overlay(Image(systemName: kind.icon).font(.system(size: 12, weight: .medium)).foregroundColor(tint))
                Text(kind.label)
                    .font(.system(size: 12.5, weight: .semibold))
                    .foregroundColor(appState.themeText)
                Text(kind.blurb)
                    .font(.system(size: 10.5))
                    .foregroundColor(appState.themeTextSecondary)
                    .lineLimit(2)
                    .multilineTextAlignment(.leading)
                    .fixedSize(horizontal: false, vertical: true)
            }
            // Equal-height cards keep the type icons on one line across a row.
            .frame(maxWidth: .infinity, minHeight: 96, alignment: .topLeading)
            .padding(12)
            .background(RoundedRectangle(cornerRadius: 10).fill(appState.themeCard.opacity(hovering ? 0.95 : 0.6)))
            .overlay(
                RoundedRectangle(cornerRadius: 10)
                    .strokeBorder(hovering ? tint.opacity(0.45) : appState.themeBorder.opacity(0.45), lineWidth: 1)
            )
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .onHover { hovering = $0 }
        .help("New \(kind.label.lowercased())")
    }
}
