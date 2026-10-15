import SwiftUI

/// Root of a secondary (aux) window. Renders one surface, pinned to the target
/// passed via `openWindow(id:"aux", value:)`. Each detail view is `isEmbedded`
/// so it loads from the explicit id and never writes the main window's shared
/// nav/tab state. No sidebar — a focused single-surface window.
struct AuxWindowRootView: View {
    let target: AuxWindowTarget?
    @Environment(AppState.self) private var appState
    /// Whoever was signed in when this first showed. A window left open
    /// across a sign-out never shows its target to the next account.
    @State private var ownerId: String?

    var body: some View {
        Group {
            if !appState.isAuthenticated {
                // macOS may restore an aux window on relaunch before sign-in;
                // don't render a detail view that would fire token-less requests.
                Text("Sign in to Werk to open this window.")
                    .font(.system(size: 13))
                    .foregroundColor(.secondary)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if let ownerId, ownerId != appState.currentUser?.id {
                Text("This window belongs to another account.")
                    .font(.system(size: 13))
                    .foregroundColor(.secondary)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                switch target {
                case .project(let id):
                    ProjectDetailView(projectId: id, isEmbedded: true)
                case .channel(let id):
                    ChannelDetailView(channelId: id, isEmbedded: true)
                case .thread(let id):
                    ThreadDetailView(threadId: id, isEmbedded: true)
                case .journal(let id):
                    JournalDetailView(journalId: id, isEmbedded: true)
                case .file(let ref):
                    // Chrome-less preview body — the split-pane headers (and
                    // the aux window title bar) already carry the filename.
                    AttachmentPreviewContent(file: ref.asProjectFile)
                case .calendar:
                    CalendarWorkspace()
                case .kanban:
                    ProductivityWorkspace()
                case .email:
                    EmailWorkspace()
                case .assistant:
                    AssistantView()
                case .journals:
                    SidePaneList(surface: .journals)
                case .channels:
                    SidePaneList(surface: .channels)
                case .threads:
                    SidePaneList(surface: .threads)
                case .workspaces:
                    SidePaneList(surface: .workspaces)
                case nil:
                    Text("Nothing to show")
                        .foregroundColor(.secondary)
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(appState.themeBg)
        .onChange(of: appState.currentUser?.id, initial: true) { _, id in
            if ownerId == nil { ownerId = id }
        }
    }
}

/// Full-pane home for archived material across all four surfaces. Reachable
/// from the sidebar footer "Archive" button. Each row opens the item (restoring
/// it to the detail pane) or restores it back to its active section.
struct ArchiveView: View {
    @Environment(AppState.self) private var appState
    @State private var projects: [MWProject] = []
    @State private var threads: [MWThread] = []
    @State private var journals: [MWJournal] = []
    @State private var channels: [ChannelSummary] = []
    @State private var isLoading = true

    private var isEmpty: Bool {
        projects.isEmpty && threads.isEmpty && journals.isEmpty && channels.isEmpty
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                HStack(spacing: 8) {
                    Image(systemName: "archivebox").foregroundColor(appState.themeAccent)
                    Text("Archive").font(.system(size: 16, weight: .semibold)).foregroundColor(appState.themeText)
                }
                if isLoading {
                    ProgressView().tint(.secondary).frame(maxWidth: .infinity).padding(.top, 40)
                } else if isEmpty {
                    Text("Nothing archived.")
                        .font(.system(size: 12)).foregroundColor(appState.themeTextSecondary)
                        .frame(maxWidth: .infinity).padding(.top, 40)
                } else {
                    if !projects.isEmpty {
                        section("Workspaces", "square.grid.2x2") {
                            ForEach(projects) { p in
                                row(p.title, "square.grid.2x2",
                                    open: { open { appState.selectedProjectId = p.id } },
                                    restore: { restoreProject(p) })
                            }
                        }
                    }
                    if !threads.isEmpty {
                        section("Threads", "bubble.left.and.bubble.right") {
                            ForEach(threads) { t in
                                row(t.title, "bubble.left.and.bubble.right",
                                    open: { open { appState.selectedThreadId = t.id } },
                                    restore: { restoreThread(t) })
                            }
                        }
                    }
                    if !journals.isEmpty {
                        section("Journals", "book.closed") {
                            ForEach(journals) { j in
                                row(j.title, "book.closed",
                                    open: { open { appState.selectedJournalId = j.id } },
                                    restore: { restoreJournal(j) })
                            }
                        }
                    }
                    if !channels.isEmpty {
                        section("Channels", "number") {
                            ForEach(channels) { c in
                                row(c.name, "number",
                                    open: { open { appState.selectedChannelId = c.id; appState.showChannelBrowse = false } },
                                    restore: { restoreChannel(c) })
                            }
                        }
                    }
                }
            }
            .padding(20)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .background(appState.themeBg)
        .task { await load() }
    }

    @ViewBuilder
    private func section<Content: View>(_ title: String, _ icon: String, @ViewBuilder _ content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title.uppercased())
                .font(.system(size: 10, weight: .semibold))
                .foregroundColor(appState.themeTextSecondary)
            content()
        }
    }

    private func row(_ title: String, _ icon: String, open: @escaping () -> Void, restore: @escaping () -> Void) -> some View {
        HStack(spacing: 8) {
            Image(systemName: icon).font(.system(size: 12)).foregroundColor(appState.themeTextSecondary).frame(width: 16)
            Text(title.isEmpty ? "Untitled" : title)
                .font(.system(size: 13)).foregroundColor(appState.themeText).lineLimit(1)
            Spacer()
            Button("Restore", action: restore)
                .buttonStyle(.plain)
                .font(.system(size: 11, weight: .medium))
                .foregroundColor(appState.themeAccent)
        }
        .padding(.horizontal, 10).padding(.vertical, 7)
        .background(appState.themeCard.opacity(0.5))
        .cornerRadius(6)
        .contentShape(Rectangle())
        .onTapGesture(perform: open)
    }

    private func open(_ select: () -> Void) {
        appState.selectedThreadId = nil; appState.selectedProjectId = nil
        appState.selectedChannelId = nil; appState.selectedJournalId = nil
        appState.showInbox = false; appState.showPeople = false; appState.showSkills = false
        appState.showChannelBrowse = false; appState.showArchive = false
        select()
    }

    private func load() async {
        async let p = (try? await MatchaWorkService.shared.listProjects(status: "archived")) ?? []
        async let t = (try? await MatchaWorkService.shared.listThreads(status: "archived")) ?? []
        async let j = (try? await JournalService.shared.listArchivedJournals()) ?? []
        async let c = (try? await ChannelsService.shared.listArchivedChannels()) ?? []
        let (pp, tt, jj, cc) = await (p, t, j, c)
        await MainActor.run {
            projects = pp; threads = tt; journals = jj; channels = cc; isLoading = false
        }
    }

    private func restoreProject(_ p: MWProject) {
        Task {
            try? await MatchaWorkService.shared.unarchiveProject(id: p.id)
            MatchaWorkService.shared.invalidateProjectLists()
            await MainActor.run { projects.removeAll { $0.id == p.id }; appState.projectsListGeneration &+= 1 }
        }
    }
    private func restoreThread(_ t: MWThread) {
        Task {
            try? await MatchaWorkService.shared.unarchiveThread(id: t.id)
            MatchaWorkService.shared.invalidateThreadLists()
            await MainActor.run {
                threads.removeAll { $0.id == t.id }
                NotificationCenter.default.post(name: .mwThreadsChanged, object: nil)
            }
        }
    }
    private func restoreJournal(_ j: MWJournal) {
        Task {
            try? await JournalService.shared.unarchiveJournal(id: j.id)
            await MainActor.run { journals.removeAll { $0.id == j.id }; appState.journalsListGeneration &+= 1 }
        }
    }
    private func restoreChannel(_ c: ChannelSummary) {
        Task {
            try? await ChannelsService.shared.unarchiveChannel(id: c.id)
            await MainActor.run { channels.removeAll { $0.id == c.id }; appState.channelsListGeneration &+= 1 }
        }
    }
}

// MARK: - Sidebar "Pinned" list

/// The only place the sidebar surfaces specific items: one list of what the
/// person pinned. Tabs (pinned with "+", closed with "×") and starred items
/// (pinned workspaces and threads, starred channels, journals and files) are
/// merged, an item that is both showing once, as its tab. Each row is a
/// coloured letter tile and a name. Hidden entirely when nothing is pinned
/// and nothing can be.
struct SidebarPinnedView: View {
    @Environment(AppState.self) private var appState
    @State private var stars: [Star] = []
    @State private var hoveredId: String?

    /// A starred item, by the same key a tab uses (`<kind>:<id>`).
    struct Star: Identifiable, Equatable {
        let entityId: String
        let name: String
        let kind: Kind
        enum Kind: String { case project, channel, thread, journal, file }
        var id: String { "\(kind.rawValue):\(entityId)" }
    }

    /// One row: a tab, a star, or both (shown as the tab).
    struct Row: Identifiable, Equatable {
        let id: String
        let name: String
        let tab: WorkTab?
        let star: Star?
    }

    /// Tabs in their order, then stars that aren't already a tab.
    nonisolated static func rows(tabs: [WorkTab], stars: [Star]) -> [Row] {
        var out = tabs.filter { $0.kind != .home }.map { Row(id: $0.id, name: $0.title, tab: $0, star: nil) }
        var seen = Set(out.map(\.id))
        for star in stars where !seen.contains(star.id) {
            seen.insert(star.id)
            out.append(Row(id: star.id, name: star.name, tab: nil, star: star))
        }
        return out
    }

    /// The tile's letter: the name's first letter or digit ("#general" → "G").
    nonisolated static func tileLetter(_ name: String) -> String {
        guard let first = name.first(where: { $0.isLetter || $0.isNumber }) else { return "•" }
        return String(first).uppercased()
    }

    /// A stable colour for an item: the same on every launch (Swift's
    /// `hashValue` is not), spread across the palette.
    nonisolated static func tileColorIndex(_ id: String, count: Int) -> Int {
        guard count > 0 else { return 0 }
        var hash: UInt32 = 5381
        for byte in id.utf8 { hash = (hash &* 33) &+ UInt32(byte) }
        return Int(hash % UInt32(count))
    }

    private static let palette: [Color] = [
        Color(red: 0.36, green: 0.55, blue: 0.95), Color(red: 0.27, green: 0.68, blue: 0.55),
        Color(red: 0.90, green: 0.55, blue: 0.25), Color(red: 0.72, green: 0.45, blue: 0.90),
        Color(red: 0.88, green: 0.38, blue: 0.48), Color(red: 0.30, green: 0.65, blue: 0.80),
        Color(red: 0.62, green: 0.58, blue: 0.30), Color(red: 0.55, green: 0.50, blue: 0.75),
    ]

    var body: some View {
        // Observe the client-side star stores so the list reloads when a
        // channel/journal/file is (un)starred — those bump their OWN
        // generation, not the list generations.
        let _ = ChannelStarStore.shared.generation
        let _ = JournalStarStore.shared.generation
        let _ = FileStarStore.shared.generation
        let rows = Self.rows(tabs: appState.openTabs, stars: stars)
        return Group {
            if !rows.isEmpty || appState.canPinActiveTab {
                VStack(alignment: .leading, spacing: 1) {
                    HStack(spacing: 6) {
                        Text("PINNED")
                            .font(.espresso(size: 10, weight: .semibold))
                            .tracking(0.6)
                            .foregroundColor(appState.themeSidebarTextSecondary.opacity(0.8))
                        Spacer(minLength: 0)
                        Button { appState.pinActiveTab() } label: {
                            Image(systemName: "plus")
                                .font(.espresso(size: 10))
                                .foregroundColor(appState.themeSidebarTextSecondary)
                                .frame(width: 18, height: 18)
                                .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                        .disabled(!appState.canPinActiveTab)
                        .opacity(appState.canPinActiveTab ? 1 : 0.3)
                        .help(pinHelp)
                    }
                    .padding(.leading, 16)
                    .padding(.trailing, 10)
                    .padding(.top, 8)
                    .padding(.bottom, 2)
                    ForEach(rows) { row in rowView(row) }
                }
            }
        }
        .task { await load() }
        .onChange(of: appState.projectsListGeneration) { _, _ in Task { await load() } }
        .onChange(of: appState.channelsListGeneration) { _, _ in Task { await load() } }
        .onChange(of: appState.journalsListGeneration) { _, _ in Task { await load() } }
        .onChange(of: ChannelStarStore.shared.generation) { _, _ in Task { await load() } }
        .onChange(of: JournalStarStore.shared.generation) { _, _ in Task { await load() } }
        .onChange(of: FileStarStore.shared.generation) { _, _ in Task { await load() } }
        .onReceive(NotificationCenter.default.publisher(for: .mwThreadsChanged)) { _ in
            Task { await load() }
        }
    }

    private var pinHelp: String {
        if appState.activeTab.kind == .home { return "Home is always open" }
        if appState.openTabs.contains(where: { $0.id == appState.activeTab.id }) { return "Already pinned" }
        if appState.pinnedTabCount >= AppState.maxPinnedTabs { return "Tab limit reached" }
        return "Pin \u{201C}\(appState.activeTab.title)\u{201D} as a tab"
    }

    private func rowView(_ row: Row) -> some View {
        let active = isActive(row)
        let hovered = hoveredId == row.id
        let unseen = row.tab.map { appState.tabUnread($0) } ?? 0
        let color = Self.palette[Self.tileColorIndex(row.id, count: Self.palette.count)]
        return Button { open(row) } label: {
            HStack(spacing: 8) {
                Text(Self.tileLetter(row.name))
                    .font(.espresso(size: 10, weight: .semibold))
                    .foregroundColor(.white)
                    .frame(width: 18, height: 18)
                    .background(RoundedRectangle(cornerRadius: 5).fill(color))
                Text(row.name)
                    .font(.espresso(size: 12, weight: active ? .medium : .regular))
                    .foregroundColor(appState.themeSidebarText.opacity(active ? 1 : 0.85))
                    .lineLimit(1)
                    .truncationMode(.tail)
                Spacer(minLength: 0)
                if unseen > 0 && !hovered {
                    Text(unseen > 10 ? "10+" : "\(unseen)")
                        .font(.espresso(size: 9, weight: .medium))
                        .foregroundColor(.white)
                        .padding(.horizontal, 5)
                        .padding(.vertical, 2)
                        .background(Capsule().fill(appState.themeSidebarAccent))
                }
                if hovered, let tab = row.tab {
                    Button { appState.closeTab(tab) } label: {
                        Image(systemName: "xmark")
                            .font(.espresso(size: 9))
                            .foregroundColor(appState.themeSidebarText.opacity(0.5))
                            .frame(width: 16, height: 16)
                            .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .help("Close tab")
                }
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 4)
            .background(
                RoundedRectangle(cornerRadius: 6)
                    .fill(active ? appState.themeSidebarAccent.opacity(0.075) : Color.clear)
            )
            .overlay(alignment: .leading) {
                if active {
                    Capsule().fill(appState.themeSidebarAccent).frame(width: 2, height: 16)
                }
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .padding(.horizontal, 6)
        .onHover { hoveredId = $0 ? row.id : (hoveredId == row.id ? nil : hoveredId) }
        .help(kindName(row))
        .contextMenu {
            if let target = paneTarget(row) {
                AuxOpenMenuButtons(target: target)
            }
            if let tab = row.tab {
                Divider()
                Button("Close tab") { appState.closeTab(tab) }
            }
        }
    }

    private func kindName(_ row: Row) -> String {
        switch row.star?.kind.rawValue ?? row.tab?.kind.rawValue {
        case "project": return "Workspace"
        case "channel": return "Channel"
        case "thread": return "Thread"
        case "journal": return "Journal"
        case "file": return "File"
        default: return ""
        }
    }

    private func paneTarget(_ row: Row) -> AuxWindowTarget? {
        if let tab = row.tab {
            switch tab.kind {
            case .project: return .project(tab.entityId)
            case .channel: return .channel(tab.entityId)
            case .thread:  return .thread(tab.entityId)
            case .journal: return .journal(tab.entityId)
            case .home:    return nil
            }
        }
        guard let star = row.star else { return nil }
        switch star.kind {
        case .project: return .project(star.entityId)
        case .channel: return .channel(star.entityId)
        case .thread:  return .thread(star.entityId)
        case .journal: return .journal(star.entityId)
        case .file:    return FileStarStore.shared.ref(for: star.entityId).map { .file($0) }
        }
    }

    private func isActive(_ row: Row) -> Bool {
        if let tab = row.tab { return appState.activeTab.id == tab.id }
        guard let star = row.star else { return false }
        switch star.kind {
        case .project: return appState.selectedProjectId == star.entityId
        case .channel: return appState.selectedChannelId == star.entityId
        case .thread:  return appState.selectedThreadId == star.entityId
        case .journal: return appState.selectedJournalId == star.entityId
        case .file:    return false
        }
    }

    private func open(_ row: Row) {
        if let tab = row.tab {
            appState.selectTab(tab)
            return
        }
        guard let star = row.star else { return }
        if star.kind == .file {
            // Files aren't a primary-pane surface — open the shared preview
            // sheet (presented by ContentView) without touching nav state.
            if let ref = FileStarStore.shared.ref(for: star.entityId) {
                appState.globalPreviewFile = ref.asProjectFile
            }
            return
        }
        appState.clearPrimaryNav()
        switch star.kind {
        case .project: appState.selectedProjectId = star.entityId
        case .channel: appState.selectedChannelId = star.entityId
        case .thread:  appState.selectedThreadId = star.entityId
        case .journal: appState.selectedJournalId = star.entityId
        case .file:    break
        }
    }

    private func load() async {
        async let pj = (try? await MatchaWorkService.shared.listProjects()) ?? []
        async let th = (try? await MatchaWorkService.shared.listThreads()) ?? []
        async let ch = (try? await ChannelsService.shared.listChannels()) ?? []
        async let jr = (try? await JournalService.shared.listJournals()) ?? []
        let projects = await pj, threads = await th, channels = await ch, journals = await jr
        let cStars = ChannelStarStore.shared
        let jStars = JournalStarStore.shared
        var out: [Star] = []
        out += projects.filter { $0.isPinned ?? false }
            .map { Star(entityId: $0.id, name: $0.title, kind: .project) }
        out += channels.filter { $0.isMember && cStars.isStarred($0.id) }
            .map { Star(entityId: $0.id, name: $0.name, kind: .channel) }
        out += journals.filter { jStars.isStarred($0.id) }
            .map { Star(entityId: $0.id, name: $0.title, kind: .journal) }
        out += threads.filter { $0.isPinned }
            .map { Star(entityId: $0.id, name: $0.displayName, kind: .thread) }
        out += FileStarStore.shared.pins
            .map { Star(entityId: $0.id, name: $0.filename, kind: .file) }
        await MainActor.run { stars = out }
    }
}

/// Personal journal folders directly beneath the Journals navigation row.
struct JournalsSidebarFolders: View {
    @Environment(AppState.self) private var appState
    @State private var folders: [MWJournalFolder] = []
    @State private var collapsed = Set<String>()
    @State private var loading = false
    @State private var failed = false
    @State private var loadGeneration = 0

    var body: some View {
        VStack(spacing: 1) {
            smartRow("All journals", icon: "tray", selection: .all)
            smartRow("Unfiled", icon: "tray.full", selection: .uncategorized)
            ForEach(JournalFolderTree.visible(folders, collapsed: collapsed), id: \.folder.id) { item in
                folderRow(item.folder, depth: item.depth)
            }
            if loading && folders.isEmpty {
                ProgressView().controlSize(.mini).padding(8)
            } else if failed {
                Button("Couldn't load folders — Retry") { Task { await load() } }
                    .font(.system(size: 10)).foregroundColor(appState.themeSidebarTextSecondary)
                    .buttonStyle(.plain).padding(8)
            } else if folders.isEmpty {
                Text("No folders yet")
                    .font(.system(size: 10)).foregroundColor(appState.themeSidebarTextSecondary)
                    .padding(8)
            }
        }
        .padding(.leading, 18).padding(.trailing, 6)
        .task(id: appState.journalsListGeneration) { await load() }
    }

    private func smartRow(_ title: String, icon: String, selection: JournalFolderSelection) -> some View {
        Button { open(selection) } label: {
            rowLabel(title, icon: icon, selected: isSelected(selection))
        }
        .buttonStyle(.plain)
    }

    private func folderRow(_ folder: MWJournalFolder, depth: Int) -> some View {
        HStack(spacing: 0) {
            if folders.contains(where: { $0.parentId == folder.id }) {
                Button {
                    if !collapsed.insert(folder.id).inserted { collapsed.remove(folder.id) }
                } label: {
                    Image(systemName: collapsed.contains(folder.id) ? "chevron.right" : "chevron.down")
                        .font(.system(size: 8)).frame(width: 16, height: 25)
                }
                .buttonStyle(.plain).foregroundColor(appState.themeSidebarTextSecondary)
                .help(collapsed.contains(folder.id) ? "Expand folder" : "Collapse folder")
            } else {
                Color.clear.frame(width: 16)
            }
            Button { open(.folder(folder.id)) } label: {
                rowLabel(folder.name, icon: "folder", selected: isSelected(.folder(folder.id)))
            }
            .buttonStyle(.plain)
        }
        .padding(.leading, CGFloat(depth) * 12)
    }

    private func rowLabel(_ title: String, icon: String, selected: Bool) -> some View {
        HStack(spacing: 6) {
            Image(systemName: icon).frame(width: 14)
            Text(title).lineLimit(1)
            Spacer(minLength: 0)
        }
        .font(.system(size: 11))
        .foregroundColor(selected ? appState.themeSidebarAccent : appState.themeSidebarTextSecondary)
        .padding(.horizontal, 6).padding(.vertical, 5)
        .background(selected ? appState.themeSidebarAccent.opacity(0.08) : .clear,
                    in: RoundedRectangle(cornerRadius: 5))
        .contentShape(Rectangle())
    }

    private func isSelected(_ selection: JournalFolderSelection) -> Bool {
        appState.showJournalsHub && appState.journalFolderSelection == selection
    }

    private func open(_ selection: JournalFolderSelection) {
        appState.clearPrimaryNav()
        appState.journalFolderSelection = selection
        appState.showJournalsHub = true
    }

    private func load() async {
        loadGeneration += 1
        let generation = loadGeneration
        let owner = appState.currentUser?.id
        loading = true
        defer { if generation == loadGeneration { loading = false } }
        do {
            let response = try await MatchaWorkService.shared.listJournalFolders()
            guard generation == loadGeneration, owner == appState.currentUser?.id, !Task.isCancelled else { return }
            folders = response
            failed = false
        } catch {
            guard generation == loadGeneration, owner == appState.currentUser?.id, !Task.isCancelled else { return }
            failed = true
        }
    }
}
