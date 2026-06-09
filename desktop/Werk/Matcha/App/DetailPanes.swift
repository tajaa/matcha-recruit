import SwiftUI

// Leaf views split out of ContentView so that frequently-churning AppState
// fields (notificationsUnreadCount, unreadInboxCount — both ticked on every
// inbound WS notification and on the 60s polls) re-render only a small badge
// instead of the whole ContentView body. ContentView.body inlines every
// @ViewBuilder computed prop + the .toolbar closure into one @Observable
// tracking scope, so a count read there rebuilds BOTH split panes (each a full
// chat tree) mid-scroll/type. Reading the counts down here keeps the panes out
// of that scope. See plan: side-by-side split scroll/type jank.

// MARK: - Detail panes

/// Primary (left) detail pane. Reads only the selection-routing fields, which
/// change on user navigation — never on a WS/poll tick — so the heavy detail
/// tree no longer rebuilds when an unread counter increments.
struct PrimaryDetailPane: View {
    @Environment(AppState.self) private var appState

    // A category "context" persists its hub (rail + grid) even while a specific
    // item is open — the hub view embeds the detail in its right pane, so the
    // rail never unmounts. Context is whichever item is selected, else whichever
    // hub flag is set. selected*Id wins so a cross-link (e.g. project → channel)
    // switches rails to the active item.
    private enum WorkCategory { case threads, projects, journals, channels }
    private var workCategory: WorkCategory? {
        if appState.selectedThreadId != nil  { return .threads }
        if appState.selectedProjectId != nil { return .projects }
        if appState.selectedChannelId != nil { return .channels }
        if appState.showThreadsHub  { return .threads }
        if appState.showProjectsHub { return .projects }
        // Journals = the Notes-style workspace. A selected journal stays inside
        // it (the workspace embeds the editor in its third column), so route to
        // .journals for either the hub flag OR a selection.
        if appState.showJournalsHub || appState.selectedJournalId != nil { return .journals }
        if appState.showChannelsHub { return .channels }
        return nil
    }

    var body: some View {
        Group {
            if let cat = workCategory {
                switch cat {
                case .threads:  ThreadsLibraryView()
                case .projects: ProjectsLibraryView()
                case .journals: JournalsWorkspace()
                case .channels: ChannelsLibraryView()
                }
            } else if let emailId = appState.selectedEmailId {
                EmailDetailView(emailId: emailId)
            } else if appState.showChannelBrowse {
                ChannelBrowseView()
            } else if appState.showInbox {
                InboxView()
            } else if appState.showPeople {
                PeopleView()
            } else if appState.showSkills {
                SkillsView()
            } else if appState.showArchive {
                ArchiveView()
            } else {
                HomeDashboardView()
            }
        }
        // Opening an item from ANY entry point (sidebar pin, recent row,
        // notification, cross-link) flips its hub on, so the hub's rail shows
        // and "back" (clearing the id) lands on the grid rather than Home.
        .onChange(of: appState.selectedThreadId)  { _, v in if v != nil { appState.showThreadsHub = true; appState.showSkills = false } }
        .onChange(of: appState.selectedProjectId) { _, v in if v != nil { appState.showProjectsHub = true } }
        .onChange(of: appState.selectedJournalId) { _, v in if v != nil { appState.showJournalsHub = true } }
        .onChange(of: appState.selectedChannelId) { _, v in if v != nil { appState.showChannelsHub = true } }
    }
}

/// Secondary (right) split pane — pinned to `target`. Renders via
/// AuxWindowRootView (isEmbedded, so it never writes shared nav state). Reads
/// only theme + the value-typed `target`, so WS/poll churn can't rebuild it.
struct SplitSecondaryPane: View {
    let target: AuxWindowTarget
    @Environment(AppState.self) private var appState
    @Environment(\.openWindow) private var openWindow

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 8) {
                Image(systemName: "rectangle.split.2x1")
                    .font(.system(size: 11))
                    .foregroundColor(appState.themeTextSecondary)
                Text(label)
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundColor(appState.themeTextSecondary)
                Spacer()
                Button {
                    openWindow(id: "aux", value: target)
                    appState.splitTarget = nil
                } label: {
                    Image(systemName: "macwindow.on.rectangle")
                        .font(.system(size: 11))
                        .foregroundColor(appState.themeTextSecondary)
                }
                .buttonStyle(.plain)
                .help("Pop out to a window")
                Button { appState.splitTarget = nil } label: {
                    Image(systemName: "xmark")
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundColor(appState.themeTextSecondary)
                }
                .buttonStyle(.plain)
                .help("Close split")
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            Divider().opacity(0.2)
            AuxWindowRootView(target: target)
        }
    }

    private var label: String {
        switch target {
        case .project: return "Project"
        case .channel: return "Channel"
        case .thread: return "Thread"
        case .journal: return "Journal"
        case .file(let ref): return ref.filename
        }
    }
}

/// Bottom (horizontal) split pane — stacks full-width beneath the top row.
/// Unlike `SplitSecondaryPane` (pinned to one target), its header carries a
/// switcher so the user can swap the pane between any thread / channel /
/// project / journal without leaving the split. Body renders via
/// AuxWindowRootView (isEmbedded), so it never touches shared nav state.
struct BottomSplitPane: View {
    let target: AuxWindowTarget
    @Environment(AppState.self) private var appState
    @Environment(\.openWindow) private var openWindow
    @State private var switcher = SplitSwitcherModel()

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 8) {
                Image(systemName: "rectangle.split.1x2")
                    .font(.system(size: 11))
                    .foregroundColor(appState.themeTextSecondary)
                Menu {
                    switcherMenu
                } label: {
                    HStack(spacing: 4) {
                        Text(switcher.title(for: target))
                            .font(.system(size: 11, weight: .semibold))
                            .foregroundColor(appState.themeTextSecondary)
                            .lineLimit(1)
                        Image(systemName: "chevron.down")
                            .font(.system(size: 8, weight: .bold))
                            .foregroundColor(appState.themeTextSecondary)
                    }
                }
                .menuStyle(.borderlessButton)
                .menuIndicator(.hidden)
                .fixedSize()
                .help("Switch what's shown here")
                Spacer()
                Button {
                    openWindow(id: "aux", value: target)
                    appState.bottomSplitTarget = nil
                } label: {
                    Image(systemName: "macwindow.on.rectangle")
                        .font(.system(size: 11))
                        .foregroundColor(appState.themeTextSecondary)
                }
                .buttonStyle(.plain)
                .help("Pop out to a window")
                Button { appState.bottomSplitTarget = nil } label: {
                    Image(systemName: "xmark")
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundColor(appState.themeTextSecondary)
                }
                .buttonStyle(.plain)
                .help("Close bottom split")
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            Divider().opacity(0.2)
            AuxWindowRootView(target: target)
        }
        .task { await switcher.loadIfNeeded() }
    }

    @ViewBuilder
    private var switcherMenu: some View {
        if !switcher.threads.isEmpty {
            Section("Threads") {
                ForEach(switcher.threads) { t in
                    Button(t.title) { appState.bottomSplitTarget = .thread(t.id) }
                }
            }
        }
        if !switcher.channels.isEmpty {
            Section("Channels") {
                ForEach(switcher.channels) { c in
                    Button("#\(c.name)") { appState.bottomSplitTarget = .channel(c.id) }
                }
            }
        }
        if !switcher.projects.isEmpty {
            Section("Projects") {
                ForEach(switcher.projects) { p in
                    Button(p.title) { appState.bottomSplitTarget = .project(p.id) }
                }
            }
        }
        if !switcher.journals.isEmpty {
            Section("Journals") {
                ForEach(switcher.journals) { j in
                    Button(j.title) { appState.bottomSplitTarget = .journal(j.id) }
                }
            }
        }
        Divider()
        Button("Reload list") { Task { await switcher.load() } }
    }
}

/// Loads the four surface lists once so the bottom-pane switcher can offer
/// them and resolve a target id back to a human title. Cheap, list-only
/// fetches; refreshed on demand via the menu's "Reload list".
@Observable
final class SplitSwitcherModel {
    var threads: [MWThread] = []
    var channels: [ChannelSummary] = []
    var projects: [MWProject] = []
    var journals: [MWJournal] = []
    private var loaded = false

    func loadIfNeeded() async {
        if !loaded { await load() }
    }

    func load() async {
        async let t = MatchaWorkService.shared.listThreads()
        async let c = ChannelsService.shared.listChannels()
        async let p = MatchaWorkService.shared.listProjects()
        async let j = MatchaWorkService.shared.listJournals()
        let tt = (try? await t) ?? []
        let cc = (try? await c) ?? []
        let pp = (try? await p) ?? []
        let jj = (try? await j) ?? []
        await MainActor.run {
            threads = tt
            channels = cc.filter { $0.isMember }
            projects = pp
            journals = jj
            loaded = true
        }
    }

    func title(for target: AuxWindowTarget) -> String {
        switch target {
        case .thread(let id):
            return threads.first { $0.id == id }?.title ?? "Thread"
        case .channel(let id):
            return channels.first { $0.id == id }.map { "#\($0.name)" } ?? "Channel"
        case .project(let id):
            return projects.first { $0.id == id }?.title ?? "Project"
        case .journal(let id):
            return journals.first { $0.id == id }?.title ?? "Journal"
        case .file(let ref):
            return ref.filename
        }
    }
}

// MARK: - Shared "open elsewhere" context-menu actions

/// The three open-elsewhere actions (new window · right split · bottom split)
/// shared by every hub's row + card context menu. Setting `splitTarget` /
/// `bottomSplitTarget` is what lights up the side/bottom panes in ContentView —
/// this is the single affordance that lets two surfaces (e.g. a journal + a
/// thread) live on screen at once. Reads only `target` + env, no churn.
struct AuxOpenMenuButtons: View {
    let target: AuxWindowTarget
    @Environment(AppState.self) private var appState
    @Environment(\.openWindow) private var openWindow

    var body: some View {
        Button { openWindow(id: "aux", value: target) } label: {
            Label("Open in New Window", systemImage: "macwindow.on.rectangle")
        }
        Button { appState.splitTarget = target } label: {
            Label("Open in Split", systemImage: "rectangle.split.2x1")
        }
        Button { appState.bottomSplitTarget = target } label: {
            Label("Open in Bottom Split", systemImage: "rectangle.split.1x2")
        }
    }
}

// MARK: - Split finder palette

/// The Cmd+F find-anything palette: Spotlight-style search over every surface
/// (thread / channel / project / journal) AND every project file. A result can
/// open into the main pane, the right split, or the bottom split (segmented
/// destination picker), and every row carries a ☆ that pins it to the
/// sidebar's Starred strip. Also reachable from the WorkTabBar magnifier.
/// Reuses SplitSwitcherModel to load + title the four surface lists; project
/// files are fanned-in separately (one cached list call per project).
struct SplitFinderPalette: View {
    @Environment(AppState.self) private var appState
    @Environment(\.dismiss) private var dismiss
    @State private var model = SplitSwitcherModel()
    @State private var search = ""
    @State private var slot: Slot = .main
    @FocusState private var searchFocused: Bool
    /// Project files across all projects, loaded after the surface lists.
    @State private var fileEntries: [FileHit] = []
    @State private var filesLoading = false
    /// Local mirror of server-side pin state so the ☆ toggles paint instantly.
    @State private var pinnedThreadIds: Set<String> = []
    @State private var pinnedProjectIds: Set<String> = []

    enum Slot: String, CaseIterable, Identifiable {
        case main = "Main Pane", right = "Right Pane", bottom = "Bottom Pane"
        var id: String { rawValue }
    }

    private struct FileHit {
        let file: MWProjectFile
        let projectTitle: String
    }

    private struct Entry: Identifiable {
        let id: String
        let target: AuxWindowTarget
        let title: String
        var subtitle: String? = nil
        let icon: String
        let group: String
    }

    var body: some View {
        // Re-render rows when a star store changes (☆ fill state).
        let _ = ChannelStarStore.shared.generation
        let _ = JournalStarStore.shared.generation
        let _ = FileStarStore.shared.generation
        VStack(spacing: 0) {
            header
            Divider().opacity(0.3)
            results
        }
        .frame(width: 520, height: 480)
        .background(appState.themeBg)
        .onExitCommand { dismiss() }
        .task {
            // Reload every open — the cached model would otherwise miss surfaces
            // created since the palette was last shown.
            await model.load()
            pinnedThreadIds = Set(model.threads.filter(\.isPinned).map(\.id))
            pinnedProjectIds = Set(model.projects.filter { $0.isPinned ?? false }.map(\.id))
            searchFocused = true
            await loadFiles()
        }
    }

    // ── Header: search + destination toggle ─────────────────────────────
    private var header: some View {
        VStack(spacing: 10) {
            HStack(spacing: 8) {
                Image(systemName: "magnifyingglass")
                    .font(.system(size: 13)).foregroundColor(appState.themeTextSecondary)
                TextField("Find a thread, channel, project, journal, or file…", text: $search)
                    .textFieldStyle(.plain)
                    .font(.system(size: 14))
                    .foregroundColor(appState.themeText)
                    .focused($searchFocused)
                    .onSubmit { if let first = filtered.first { open(first) } }
                if filesLoading {
                    ProgressView().controlSize(.small)
                        .help("Indexing project files…")
                }
                if !search.isEmpty {
                    Button { search = "" } label: {
                        Image(systemName: "xmark.circle.fill")
                            .font(.system(size: 12)).foregroundColor(appState.themeTextSecondary)
                    }
                    .buttonStyle(.plain)
                }
            }
            Picker("", selection: $slot) {
                ForEach(Slot.allCases) { s in
                    Text(label(for: s)).tag(s)
                }
            }
            .pickerStyle(.segmented)
            .labelsHidden()
        }
        .padding(14)
    }

    /// Annotate a slot with "(replace)" so picking it reads as a replace.
    private func label(for s: Slot) -> String {
        let occupied = (s == .right && appState.splitTarget != nil)
            || (s == .bottom && appState.bottomSplitTarget != nil)
        return occupied ? "\(s.rawValue) (replace)" : s.rawValue
    }

    // ── Results list ────────────────────────────────────────────────────
    private var allEntries: [Entry] {
        var out: [Entry] = []
        out += model.threads.map { Entry(id: "t:\($0.id)", target: .thread($0.id), title: $0.displayName, icon: "bubble.left.and.bubble.right", group: "Threads") }
        out += model.channels.map { Entry(id: "c:\($0.id)", target: .channel($0.id), title: "#\($0.name)", icon: "number", group: "Channels") }
        out += model.projects.map { Entry(id: "p:\($0.id)", target: .project($0.id), title: $0.title, icon: "folder", group: "Projects") }
        out += model.journals.map { Entry(id: "j:\($0.id)", target: .journal($0.id), title: $0.title, icon: "book.closed", group: "Journals") }
        out += fileEntries.map { hit in
            Entry(id: "f:\(hit.file.id)", target: .file(MWFileRef(file: hit.file)),
                  title: hit.file.filename, subtitle: hit.projectTitle,
                  icon: hit.file.isImage ? "photo" : "doc", group: "Files")
        }
        return out
    }

    private var filtered: [Entry] {
        guard !search.isEmpty else { return allEntries }
        return allEntries.filter {
            $0.title.localizedCaseInsensitiveContains(search)
                || ($0.subtitle?.localizedCaseInsensitiveContains(search) ?? false)
        }
    }

    private let groupOrder = ["Threads", "Channels", "Projects", "Journals", "Files"]

    @ViewBuilder
    private var results: some View {
        if filtered.isEmpty {
            VStack(spacing: 8) {
                Spacer()
                Image(systemName: "magnifyingglass")
                    .font(.system(size: 22)).foregroundColor(appState.themeTextSecondary.opacity(0.6))
                Text(search.isEmpty ? "Nothing to open yet" : "No matches")
                    .font(.system(size: 12)).foregroundColor(appState.themeTextSecondary)
                Spacer()
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else {
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 1) {
                    ForEach(groupOrder, id: \.self) { group in
                        let rows = filtered.filter { $0.group == group }
                        if !rows.isEmpty {
                            Text(group.uppercased())
                                .font(.system(size: 9, weight: .semibold)).tracking(0.5)
                                .foregroundColor(appState.themeTextSecondary)
                                .padding(.horizontal, 14).padding(.top, 12).padding(.bottom, 4)
                            ForEach(rows) { entry in row(entry) }
                        }
                    }
                }
                .padding(.bottom, 10)
            }
        }
    }

    private func row(_ entry: Entry) -> some View {
        HStack(spacing: 0) {
            Button { open(entry) } label: {
                HStack(spacing: 9) {
                    Image(systemName: entry.icon)
                        .font(.system(size: 12)).foregroundColor(appState.themeAccent).frame(width: 16)
                    Text(entry.title.isEmpty ? "Untitled" : entry.title)
                        .font(.system(size: 13)).foregroundColor(appState.themeText).lineLimit(1)
                    if let sub = entry.subtitle {
                        Text(sub)
                            .font(.system(size: 11)).foregroundColor(appState.themeTextSecondary)
                            .lineLimit(1)
                    }
                    Spacer(minLength: 0)
                }
                .padding(.leading, 14).padding(.vertical, 7)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)

            // ☆ — add/remove from the sidebar Starred strip without opening.
            let starred = isStarred(entry)
            Button { toggleStar(entry) } label: {
                Image(systemName: starred ? "star.fill" : "star")
                    .font(.system(size: 11))
                    .foregroundColor(starred ? .yellow : appState.themeTextSecondary.opacity(0.55))
                    .frame(width: 26, height: 26)
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .padding(.trailing, 8)
            .help(starred ? "Remove from sidebar Starred" : "Add to sidebar Starred")
        }
    }

    // ── Star (pin to sidebar) ───────────────────────────────────────────

    private func isStarred(_ entry: Entry) -> Bool {
        switch entry.target {
        case .thread(let id):  return pinnedThreadIds.contains(id)
        case .project(let id): return pinnedProjectIds.contains(id)
        case .channel(let id): return ChannelStarStore.shared.isStarred(id)
        case .journal(let id): return JournalStarStore.shared.isStarred(id)
        case .file(let ref):   return FileStarStore.shared.isStarred(ref.id)
        }
    }

    private func toggleStar(_ entry: Entry) {
        switch entry.target {
        case .thread(let id):
            let nowPinned = !pinnedThreadIds.contains(id)
            if nowPinned { pinnedThreadIds.insert(id) } else { pinnedThreadIds.remove(id) }
            Task {
                _ = try? await MatchaWorkService.shared.setPinned(id: id, pinned: nowPinned)
                NotificationCenter.default.post(name: .mwThreadsChanged, object: nil)
            }
        case .project(let id):
            let nowPinned = !pinnedProjectIds.contains(id)
            if nowPinned { pinnedProjectIds.insert(id) } else { pinnedProjectIds.remove(id) }
            Task {
                _ = try? await MatchaWorkService.shared.updateProjectMeta(id: id, isPinned: nowPinned)
                MatchaWorkService.shared.invalidateProjectLists()
                await MainActor.run { appState.projectsListGeneration &+= 1 }
            }
        case .channel(let id):
            ChannelStarStore.shared.toggle(id)
        case .journal(let id):
            JournalStarStore.shared.toggle(id)
        case .file(let ref):
            FileStarStore.shared.toggle(ref)
        }
    }

    // ── Open ────────────────────────────────────────────────────────────

    private func open(_ entry: Entry) {
        switch slot {
        case .main:
            if case .file(let ref) = entry.target {
                // Sheet-over-sheet doesn't present reliably — let this palette
                // fully dismiss before raising the preview sheet.
                dismiss()
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
                    appState.globalPreviewFile = ref.asProjectFile
                }
                return
            }
            appState.clearPrimaryNav()
            switch entry.target {
            case .project(let id): appState.selectedProjectId = id
            case .channel(let id): appState.selectedChannelId = id
            case .thread(let id):  appState.selectedThreadId = id
            case .journal(let id): appState.selectedJournalId = id
            case .file: break
            }
        case .right:  appState.splitTarget = entry.target
        case .bottom: appState.bottomSplitTarget = entry.target
        }
        dismiss()
    }

    // ── Files index ─────────────────────────────────────────────────────

    /// Fan-in file lists for every project (the per-project endpoint is cached
    /// service-side, so re-opening the palette is cheap). Sorted by project
    /// then filename so the Files group reads grouped.
    private func loadFiles() async {
        guard !model.projects.isEmpty else { return }
        filesLoading = true
        let projects = model.projects
        var out: [FileHit] = []
        await withTaskGroup(of: [FileHit].self) { group in
            for p in projects {
                group.addTask {
                    let files = (try? await MatchaWorkService.shared.listProjectFiles(projectId: p.id)) ?? []
                    return files.map { FileHit(file: $0, projectTitle: p.title) }
                }
            }
            for await chunk in group { out += chunk }
        }
        out.sort {
            ($0.projectTitle, $0.file.filename.lowercased())
                < ($1.projectTitle, $1.file.filename.lowercased())
        }
        fileEntries = out
        filesLoading = false
    }
}

// MARK: - Churning-counter leaf badges

/// Toolbar bell label. Reads `notificationsUnreadCount` here so its ticks
/// re-render only this badge, not ContentView. The Button + popover stay in
/// ContentView (they own the `showNotifications` @State).
struct NotificationBellBadge: View {
    @Environment(AppState.self) private var appState

    var body: some View {
        ZStack(alignment: .topTrailing) {
            Image(systemName: "bell")
                .font(.system(size: 13))
                .foregroundColor(appState.themeText.opacity(0.7))
            if appState.notificationsUnreadCount > 0 {
                Text(appState.notificationsUnreadCount > 9 ? "9+" : "\(appState.notificationsUnreadCount)")
                    .font(.system(size: 8, weight: .bold))
                    .foregroundColor(.white)
                    .padding(.horizontal, 3)
                    .padding(.vertical, 1)
                    .background(Color.red)
                    .clipShape(Capsule())
                    .offset(x: 6, y: -5)
            }
        }
        .frame(width: 22, height: 16)
    }
}

/// Reusable sidebar footer button. Theme reads only (non-churning).
struct SidebarFooterButton: View {
    let icon: String
    let label: String
    var badge: Int = 0
    let isActive: Bool
    let action: () -> Void
    @Environment(AppState.self) private var appState

    var body: some View {
        Button(action: action) {
            HStack(spacing: 5) {
                Image(systemName: icon)
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(isActive ? appState.themeAccent : appState.themeTextSecondary)
                Text(label)
                    .font(.system(size: 12, weight: isActive ? .semibold : .regular))
                    .foregroundColor(isActive ? appState.themeAccent : appState.themeText.opacity(0.85))
                    .lineLimit(1)
                    .fixedSize(horizontal: true, vertical: false)
                if badge > 0 {
                    Text("\(badge)")
                        .font(.system(size: 9, weight: .bold))
                        .foregroundColor(.white)
                        .padding(.horizontal, 5)
                        .padding(.vertical, 1)
                        .background(appState.themeAccent)
                        .clipShape(Capsule())
                }
                Spacer()
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .background(
                RoundedRectangle(cornerRadius: 6)
                    .fill(isActive ? appState.themeAccent.opacity(0.14) : Color.clear)
            )
        }
        .buttonStyle(.plain)
    }
}

/// Inbox footer button. Reads `unreadInboxCount` (and `showInbox`) here so its
/// ticks re-render only this button, not ContentView. `action` is supplied by
/// ContentView (it mutates the shared nav flags).
struct InboxFooterButton: View {
    let action: () -> Void
    @Environment(AppState.self) private var appState

    var body: some View {
        SidebarFooterButton(
            icon: "envelope",
            label: "Inbox",
            badge: appState.unreadInboxCount,
            isActive: appState.showInbox,
            action: action
        )
    }
}
