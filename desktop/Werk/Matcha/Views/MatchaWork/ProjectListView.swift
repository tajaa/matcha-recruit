import SwiftUI
import AppKit

struct ProjectListView: View {
    @Environment(AppState.self) private var appState
    @Environment(\.openWindow) private var openWindow
    var showHeader: Bool = true
    var searchText: String = ""

    @State private var projects: [MWProject] = []
    @State private var isLoading = true
    @State private var isCreating = false
    @State private var showTypePicker = false
    @State private var showNewBlog = false

    @State private var visibleCount = 3
    private let pageSize = 3

    @State private var projectToArchive: MWProject?

    // MARK: - Computed lists

    private var sidebarProjects: [MWProject] {
        projects
            .filter { p in
                p.status != "archived" &&
                (searchText.isEmpty || p.title.localizedCaseInsensitiveContains(searchText)) &&
                ((p.isPinned ?? false) || isRecentlyActive(p.updatedAt))
            }
            .pinnedFirst()
    }

    private func isRecentlyActive(_ dateString: String?, days: Int = 7) -> Bool {
        guard let ds = dateString, let date = parseMWDate(ds) else { return true }
        return Date().timeIntervalSince(date) < Double(days) * 86_400
    }

    // MARK: - Body

    var body: some View {
        VStack(spacing: 0) {
            if showHeader {
                headerView
                Divider().opacity(0.3)
            }

            if isLoading {
                Spacer()
                ProgressView().tint(.secondary)
                Spacer()
            } else if projects.isEmpty {
                Spacer()
                VStack(spacing: 8) {
                    Image(systemName: "folder")
                        .font(.system(size: 28))
                        .foregroundColor(.secondary)
                    Text("No projects yet")
                        .font(.system(size: 13))
                        .foregroundColor(.secondary)
                }
                Spacer()
            } else if sidebarProjects.isEmpty {
                VStack(spacing: 8) {
                    Image(systemName: "clock")
                        .font(.system(size: 22))
                        .foregroundColor(.secondary)
                    Text("No recent projects")
                        .font(.system(size: 11))
                        .foregroundColor(.secondary)
                    Text("Check Home for older work")
                        .font(.system(size: 10))
                        .foregroundColor(.secondary.opacity(0.7))
                }
                .frame(maxWidth: .infinity, alignment: .center)
                .padding(.vertical, 16)
            } else {
                let limit = searchText.isEmpty ? visibleCount : sidebarProjects.count
                LazyVStack(spacing: 0) {
                    ForEach(sidebarProjects.prefix(limit)) { p in
                        projectRow(p)
                    }
                    if searchText.isEmpty && sidebarProjects.count > visibleCount {
                        SidebarShowMoreButton(remaining: sidebarProjects.count - visibleCount, pageSize: pageSize) {
                            visibleCount += pageSize
                        }
                    }
                }
                .padding(.vertical, 4)
            }
        }
        .background(Color.clear)
        .task(id: appState.projectsListGeneration) { await load() }
        .onChange(of: searchText) { _, _ in
            visibleCount = 3
        }
        .onReceive(NotificationCenter.default.publisher(for: .mwProjectTitlePatched)) { note in
            guard let patch = note.object as? MWProjectTitlePatch else { return }
            if let i = projects.firstIndex(where: { $0.id == patch.id }) {
                projects[i].title = patch.title
            }
        }
        .onReceive(NotificationCenter.default.publisher(for: .mwProjectDataChanged)) { _ in
            MatchaWorkService.shared.invalidateProjectLists()
            Task { await load() }
        }
        .sheet(isPresented: $showNewBlog) {
            NewBlogSheet { proj in
                projects.insert(proj, at: 0)
                appState.selectedProjectId = proj.id
                appState.selectedThreadId = nil
                appState.selectedJournalId = nil
                appState.projectsListGeneration &+= 1
            }
        }
        .confirmationDialog(
            projectToArchive.map { "Archive \"\($0.title)\"?" } ?? "Archive project?",
            isPresented: Binding(
                get: { projectToArchive != nil },
                set: { if !$0 { projectToArchive = nil } }
            ),
            titleVisibility: .visible,
            presenting: projectToArchive
        ) { p in
            Button("Archive", role: .destructive) {
                Task {
                    try? await MatchaWorkService.shared.archiveProject(id: p.id)
                    await MainActor.run {
                        if appState.selectedProjectId == p.id { appState.selectedProjectId = nil }
                        projectToArchive = nil
                    }
                    await load()
                }
            }
            Button("Cancel", role: .cancel) {}
        } message: { p in
            if p.projectType == "collab" {
                Text("This will archive the collab project for all collaborators.")
            } else {
                Text("The project will be hidden from your sidebar. You can unarchive it from the context menu.")
            }
        }
    }

    // MARK: - Header

    private var headerView: some View {
        HStack {
            Text("Projects")
                .font(.system(size: 13, weight: .semibold))
                .foregroundColor(.secondary)
            Spacer()
            Button { showTypePicker = true } label: {
                Image(systemName: "plus")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(.secondary)
                    .frame(width: 24, height: 24)
                    .background(Color.zinc800)
                    .cornerRadius(6)
            }
            .buttonStyle(.plain)
            .disabled(isCreating)
            .popover(isPresented: $showTypePicker) { newProjectMenu }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 10)
    }

    private var newProjectMenu: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("New Project")
                .font(.system(size: 12, weight: .semibold))
                .foregroundColor(.secondary)
                .padding(.bottom, 4)
            ForEach(["general", "presentation", "recruiting", "collab", "discipline"], id: \.self) { type in
                Button {
                    showTypePicker = false
                    createProject(type: type)
                } label: {
                    HStack {
                        Image(systemName: iconForType(type))
                            .font(.system(size: 11))
                            .frame(width: 16)
                        Text(labelForType(type))
                            .font(.system(size: 12))
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.vertical, 4)
                }
                .buttonStyle(.plain)
                .foregroundColor(.white)
            }
            Button {
                showTypePicker = false
                showNewBlog = true
            } label: {
                HStack {
                    Image(systemName: "doc.richtext")
                        .font(.system(size: 11))
                        .frame(width: 16)
                    Text("Blog Post")
                        .font(.system(size: 12))
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.vertical, 4)
            }
            .buttonStyle(.plain)
            .foregroundColor(.white)
        }
        .padding(12)
        .frame(width: 180)
    }

    // MARK: - Row builders

    private func projectRow(_ p: MWProject) -> some View {
        let selected = appState.selectedProjectId == p.id
        return Button {
            appState.selectedProjectId = p.id
            appState.selectedThreadId = nil
            appState.selectedJournalId = nil
            appState.selectedChannelId = nil
            appState.showInbox = false
            appState.showSkills = false
        } label: {
            ProjectSidebarRowContent(
                project: p,
                isSelected: selected,
                onTogglePin: { Task { await togglePin(project: p) } },
                onArchive: { projectToArchive = p }
            )
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
            .sidebarRowStyle(isSelected: selected)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .contextMenu {
            Button {
                openWindow(id: "aux", value: AuxWindowTarget.project(p.id))
            } label: {
                Label("Open in new window", systemImage: "macwindow.on.rectangle")
            }
            Button {
                appState.splitTarget = .project(p.id)
            } label: {
                Label("Open in split", systemImage: "rectangle.split.2x1")
            }
            Button {
                appState.bottomSplitTarget = .project(p.id)
            } label: {
                Label("Open in bottom split", systemImage: "rectangle.split.1x2")
            }
            Divider()
            Button((p.isPinned ?? false) ? "Unstar" : "Star") {
                Task { await togglePin(project: p) }
            }
            Menu("Export") {
                Button("PDF") { Task { await exportProject(p, format: "pdf") } }
                Button("Markdown") { Task { await exportProject(p, format: "md") } }
                Button("DOCX") { Task { await exportProject(p, format: "docx") } }
            }
            Button("Archive") { projectToArchive = p }
            Divider()
            Button("Delete…") {
                let alert = NSAlert()
                alert.messageText = "Delete \"\(p.title)\"?"
                alert.informativeText = "Permanently deletes the project, its sections, and all associated threads and messages. Cannot be undone."
                alert.alertStyle = .critical
                alert.addButton(withTitle: "Delete Permanently")
                alert.addButton(withTitle: "Cancel")
                if alert.runModal() == .alertFirstButtonReturn {
                    Task {
                        try? await MatchaWorkService.shared.deleteProject(id: p.id)
                        await MainActor.run {
                            if appState.selectedProjectId == p.id { appState.selectedProjectId = nil }
                            appState.projectsListGeneration &+= 1
                        }
                        await load()
                    }
                }
            }
        }
    }

    // MARK: - Section header (Archived only)

    private func projectSectionHeader(title: String, icon: String, count: Int, isExpanded: Binding<Bool>) -> some View {
        Button {
            withAnimation(.easeOut(duration: 0.15)) {
                isExpanded.wrappedValue.toggle()
            }
        } label: {
            HStack(spacing: 4) {
                Image(systemName: isExpanded.wrappedValue ? "chevron.down" : "chevron.right")
                    .font(.system(size: 8, weight: .semibold))
                    .foregroundColor(.secondary)
                    .frame(width: 10, alignment: .leading)
                Image(systemName: icon)
                    .font(.system(size: 9, weight: .medium))
                    .foregroundColor(.secondary)
                Text(title)
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundColor(.secondary)
                Spacer()
                Text("\(count)")
                    .font(.system(size: 9, weight: .medium))
                    .foregroundColor(.secondary.opacity(0.6))
            }
            .contentShape(Rectangle())
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
        }
        .buttonStyle(.plain)
    }

    private func sectionSubtitle(_ p: MWProject) -> String {
        let s = p.sections?.count ?? 0
        let c = p.chatCount ?? 0
        return "\(s) section\(s == 1 ? "" : "s") · \(c) chat\(c == 1 ? "" : "s")"
    }

    // MARK: - Data

    private func load() async {
        do {
            let p = try await MatchaWorkService.shared.listProjects()
            await MainActor.run {
                projects = p
                isLoading = false
            }
        } catch {
            await MainActor.run { isLoading = false }
        }
    }

    @MainActor
    private func exportProject(_ project: MWProject, format: String) async {
        do {
            let data = try await MatchaWorkService.shared.exportProject(projectId: project.id, format: format)
            guard !data.isEmpty else { return }
            presentExportSavePanel(data: data, format: format, title: project.title)
        } catch {
            let alert = NSAlert()
            alert.messageText = "Export failed"
            alert.informativeText = error.localizedDescription
            alert.alertStyle = .warning
            alert.runModal()
        }
    }

    private func togglePin(project: MWProject) async {
        let nextPinned = !(project.isPinned ?? false)
        await MainActor.run {
            if let i = projects.firstIndex(where: { $0.id == project.id }) {
                projects[i].isPinned = nextPinned
            }
        }
        do {
            _ = try await MatchaWorkService.shared.setProjectPinned(id: project.id, pinned: nextPinned)
            await MainActor.run { appState.projectsListGeneration &+= 1 }
        } catch {
            await MainActor.run {
                if let i = projects.firstIndex(where: { $0.id == project.id }) {
                    projects[i].isPinned = !nextPinned
                }
            }
            print("[ProjectListView] togglePin failed: \(error)")
        }
    }

    private func createProject(type: String) {
        isCreating = true
        Task {
            do {
                let proj = try await MatchaWorkService.shared.createProject(title: "New Project", projectType: type)
                await MainActor.run {
                    projects.insert(proj, at: 0)
                    appState.selectedProjectId = proj.id
                    appState.selectedThreadId = nil
                    appState.selectedJournalId = nil
                    appState.projectsListGeneration &+= 1
                    isCreating = false
                }
            } catch {
                await MainActor.run {
                    isCreating = false
                    let alert = NSAlert()
                    alert.messageText = "Couldn't create project"
                    alert.informativeText = error.localizedDescription
                    alert.alertStyle = .warning
                    alert.runModal()
                }
            }
        }
    }

    private func iconForType(_ type: String) -> String {
        switch type {
        case "general": return "doc.text"
        case "presentation": return "rectangle.on.rectangle"
        case "recruiting": return "person.3"
        case "collab": return "person.2.crop.square.stack"
        case "discipline": return "exclamationmark.shield"
        default: return "doc.text"
        }
    }

    private func labelForType(_ type: String) -> String {
        switch type {
        case "collab": return "Collab"
        case "discipline": return "Disciplinary Action"
        default: return type.capitalized
        }
    }
}

// MARK: - Project sidebar row content (manages its own hover state)

private struct ProjectSidebarRowContent: View {
    @Environment(AppState.self) private var appState
    let project: MWProject
    var isSelected: Bool = false
    let onTogglePin: () -> Void
    let onArchive: () -> Void

    @State private var isHovered = false

    var body: some View {
        HStack(spacing: 6) {
            // Leading: the project's chosen icon (defaults to "folder"), like
            // journals. Pin state is shown via the hover star + context menu.
            Image(systemName: project.icon ?? "folder")
                .font(.system(size: 11))
                .foregroundColor(appState.themeAccent)
                .frame(width: 16)

            Text(project.title)
                .font(.system(size: 13, weight: isSelected ? .bold : .regular))
                .foregroundColor(appState.themeText)
                .lineLimit(1)

            if let type = project.projectType, !type.isEmpty {
                Text(type)
                    .font(.system(size: 9, weight: .medium))
                    .foregroundColor(typeBadgeColor)
                    .padding(.horizontal, 5)
                    .padding(.vertical, 1)
                    .background(typeBadgeColor.opacity(0.14))
                    .cornerRadius(3)
                    .lineLimit(1)
            }

            Spacer(minLength: 4)

            // Hover → star toggle; otherwise a small collaborator avatar.
            if isHovered {
                Button(action: onTogglePin) {
                    Image(systemName: (project.isPinned ?? false) ? "star.fill" : "star")
                        .font(.system(size: 11))
                        .foregroundColor((project.isPinned ?? false) ? appState.themeAccent : appState.themeTextSecondary)
                }
                .buttonStyle(.plain)
                .help((project.isPinned ?? false) ? "Unstar" : "Star")
            } else if let other = firstCollaborator {
                collaboratorAvatar(other)
            }
        }
        .padding(.vertical, 3)
        .onHover { isHovered = $0 }
    }

    /// Project-type badge gray, tuned per theme: light gray on dark, dark gray
    /// on light, mid gray on cappuchin (so it reads as muted, not as an accent).
    private var typeBadgeColor: Color {
        switch appState.appTheme {
        case "light": return Color(white: 0.35)
        case "platinum": return Color(white: 0.30)
        case "cappuchin": return Color(white: 0.5)
        case "graphite": return Color(white: 0.62)
        default: return Color(white: 0.72)  // dark
        }
    }

    private var firstCollaborator: MWProjectCollaborator? {
        project.collaborators?.first { $0.userId != appState.currentUser?.id }
    }

    @ViewBuilder
    private func collaboratorAvatar(_ c: MWProjectCollaborator) -> some View {
        Group {
            if let urlStr = c.avatarUrl, let url = URL(string: urlStr) {
                AsyncImage(url: url) { phase in
                    if case .success(let img) = phase {
                        img.resizable().aspectRatio(contentMode: .fill)
                    } else {
                        avatarInitials(c.name)
                    }
                }
            } else {
                avatarInitials(c.name)
            }
        }
        .frame(width: 18, height: 18)
        .clipShape(Circle())
        .help(c.name)
    }

    private func avatarInitials(_ name: String) -> some View {
        Circle()
            .fill(appState.themeAccent.opacity(0.25))
            .overlay(
                Text(String(name.first ?? "?").uppercased())
                    .font(.system(size: 9, weight: .semibold))
                    .foregroundColor(appState.themeAccent)
            )
    }
}

// MARK: - Array helper

private extension Array where Element == MWProject {
    func pinnedFirst() -> [MWProject] {
        enumerated().sorted { lhs, rhs in
            let lp = lhs.element.isPinned ?? false
            let rp = rhs.element.isPinned ?? false
            if lp != rp { return lp && !rp }
            return lhs.offset < rhs.offset
        }.map { $0.element }
    }
}

// MARK: - Collaborator summary

struct CollaboratorRowSummary: View {
    @Environment(AppState.self) private var appState
    let others: [MWProjectCollaborator]
    private let maxNames = 2

    private var displayText: String {
        let visible = Array(others.prefix(maxNames))
        let names = visible.map { firstName($0.name) }
        let overflow = others.count - visible.count
        let joined = names.joined(separator: ", ")
        return overflow > 0 ? "\(joined) +\(overflow)" : joined
    }

    private var tooltip: String {
        others.map { c in
            c.role == "owner" ? "\(c.name) (owner)" : c.name
        }.joined(separator: ", ")
    }

    var body: some View {
        HStack(spacing: 3) {
            Image(systemName: "person.2.fill")
                .font(.system(size: 8))
                .foregroundColor(appState.themeTextSecondary)
            Text(displayText)
                .font(.system(size: 10))
                .foregroundColor(appState.themeTextSecondary)
                .lineLimit(1)
        }
        .padding(.horizontal, 5).padding(.vertical, 1)
        .background(appState.themeAccent.opacity(0.08))
        .cornerRadius(3)
        .help(tooltip)
    }

    private func firstName(_ full: String) -> String {
        String(full.split(separator: " ").first ?? Substring(full))
    }
}

// MARK: - Projects hub (full-pane dashboard)

/// Full-pane "Projects" hub — opened by clicking the sidebar Projects nav row.
/// The sidebar is nav-only; all projects are listed / filtered / created here.
/// Picking a card sets `selectedProjectId` so the detail opens OVER the hub
/// (the hub flag stays set, so closing the project returns here).
struct ProjectsLibraryView: View {
    @Environment(AppState.self) private var appState

    @State private var projects: [MWProject] = []
    @State private var isLoading = true
    @State private var search = ""
    @State private var filter: Filter = .all
    @State private var showTypePicker = false
    @State private var railSearch = ""
    @State private var railCollapsed = false

    enum Filter: String, CaseIterable, Identifiable {
        case all = "All", pinned = "Pinned"
        var id: String { rawValue }
    }

    private let columns = [GridItem(.adaptive(minimum: 200, maximum: 280), spacing: 14)]
    private let types: [(type: String, label: String, icon: String)] = [
        ("general", "General", "folder"),
        ("presentation", "Presentation", "rectangle.on.rectangle.angled"),
        ("recruiting", "Recruiting", "person.2"),
        ("collab", "Collab", "person.3.sequence"),
    ]

    var body: some View {
        HSplitView {
            if railCollapsed {
                MWHubRailStrip { railCollapsed = false }
            } else {
                rail.frame(minWidth: 232, idealWidth: 258, maxWidth: 320)
            }
            Group {
                if let id = appState.selectedProjectId {
                    ProjectDetailView(projectId: id)
                } else {
                    VStack(spacing: 0) {
                        header
                        Divider().background(appState.themeBorder)
                        content
                    }
                    .background(ThemeRadialBackground())
                }
            }
            .frame(minWidth: 420, maxWidth: .infinity, maxHeight: .infinity)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .task { await load() }
        .onChange(of: appState.projectsListGeneration) { _, _ in Task { await load() } }
    }

    // ── Rail ────────────────────────────────────────────────────────────
    private var railProjects: [MWProject] {
        var out = projects
        if !railSearch.isEmpty { out = out.filter { $0.title.localizedCaseInsensitiveContains(railSearch) } }
        return out.sorted { ($0.isPinned ?? false) && !($1.isPinned ?? false) }
    }

    private var rail: some View {
        MWHubRail {
            VStack(spacing: 8) {
                HStack {
                    Text("Projects").font(.system(size: 12, weight: .semibold)).foregroundColor(appState.themeTextSecondary)
                    Spacer()
                    MWHubRailIconButton(icon: "sidebar.left", help: "Hide sidebar") { railCollapsed = true }
                    MWHubRailIconButton(icon: "plus", help: "New project") { showTypePicker = true }
                        .popover(isPresented: $showTypePicker) { typeMenu }
                }
                HStack(spacing: 6) {
                    Image(systemName: "line.3.horizontal.decrease").font(.system(size: 10)).foregroundColor(appState.themeTextSecondary)
                    TextField("Filter", text: $railSearch).textFieldStyle(.plain)
                        .font(.system(size: 11)).foregroundColor(appState.themeText)
                }
                .padding(.horizontal, 8).padding(.vertical, 5)
                .background(Capsule().fill(appState.themeText.opacity(0.06)))
            }
        } rows: {
            MWHubRailRow(icon: "square.grid.2x2", title: "All Projects",
                         selected: appState.selectedProjectId == nil) {
                appState.selectedProjectId = nil
            }
            ForEach(railProjects) { p in
                MWHubRailRow(icon: p.icon ?? "folder",
                             title: p.title,
                             selected: appState.selectedProjectId == p.id,
                             accent: p.isPinned ?? false) { open(p) }
                    .contextMenu {
                        Button(p.isPinned ?? false ? "Unpin" : "Pin") { Task { await togglePin(p) } }
                        Divider()
                        AuxOpenMenuButtons(target: .project(p.id))
                        Divider()
                        Button("Archive") { Task { await archive(p) } }
                        Button("Delete…") { confirmDelete(p) }
                    }
            }
            // Panel nav for the open collab project — replaces the horizontal
            // tab strip that used to sit above the detail pane. Switching goes
            // through pendingProjectPanel (the deep-link relay the detail view
            // already consumes); highlight mirrors activeProjectPanel.
            if let pid = appState.selectedProjectId,
               projects.first(where: { $0.id == pid })?.projectType == "collab" {
                Divider().opacity(0.25).padding(.vertical, 6)
                Text("PROJECT")
                    .font(.system(size: 9, weight: .semibold))
                    .tracking(0.6)
                    .foregroundColor(appState.themeTextSecondary)
                    .padding(.horizontal, 10)
                    .padding(.bottom, 2)
                    .frame(maxWidth: .infinity, alignment: .leading)
                ForEach(CollabRightPanel.allCases.filter { $0 != .threads }) { panel in
                    MWHubRailRow(icon: panel.icon,
                                 title: panel.label,
                                 selected: appState.activeProjectPanel == panel) {
                        appState.pendingProjectPanel = panel
                    }
                }
            }
        }
    }

    private var typeMenu: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("New Project").font(.system(size: 12, weight: .semibold))
                .foregroundColor(appState.themeTextSecondary).padding(.bottom, 4)
            ForEach(types, id: \.type) { t in
                Button { showTypePicker = false; create(type: t.type) } label: {
                    HStack { Image(systemName: t.icon).frame(width: 16); Text(t.label).font(.system(size: 12)); Spacer() }
                        .padding(.vertical, 4).contentShape(Rectangle())
                }
                .buttonStyle(.plain).foregroundColor(appState.themeText)
            }
        }
        .padding(12).frame(width: 200)
    }

    private var shown: [MWProject] {
        var out = projects
        if filter == .pinned { out = out.filter { $0.isPinned ?? false } }
        if !search.isEmpty { out = out.filter { $0.title.localizedCaseInsensitiveContains(search) } }
        return out.sorted { ($0.isPinned ?? false) && !($1.isPinned ?? false) }
    }

    private var header: some View {
        VStack(spacing: 12) {
            HStack(alignment: .center) {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Projects").font(.system(size: 20, weight: .bold)).foregroundColor(appState.themeText)
                    Text("Workspaces, presentations, and collab boards")
                        .font(.system(size: 12)).foregroundColor(appState.themeTextSecondary)
                }
                Spacer()
                newButton
            }
            HStack(spacing: 8) {
                ForEach(Filter.allCases) { f in MWHubPill(label: f.rawValue, selected: filter == f) { filter = f } }
                Spacer()
                MWHubSearch(text: $search)
            }
        }
        .padding(20)
    }

    private var newButton: some View {
        // Popover is anchored on the always-present rail "+" button, so this
        // header button just toggles the shared state.
        Button { showTypePicker = true } label: {
            HStack(spacing: 5) { Image(systemName: "plus"); Text("New Project").font(.system(size: 12, weight: .semibold)) }
                .padding(.horizontal, 12).padding(.vertical, 7)
                .background(appState.themeAccent).foregroundColor(appState.themeOnAccent).cornerRadius(8)
        }
        .buttonStyle(.plain)
    }

    @ViewBuilder private var content: some View {
        if isLoading {
            Spacer(); ProgressView().tint(appState.themeTextSecondary); Spacer()
        } else if shown.isEmpty {
            MWHubEmpty(icon: "folder",
                       title: search.isEmpty && filter == .all ? "No projects yet" : "Nothing here",
                       cta: "New Project") { showTypePicker = true }
        } else {
            ScrollView {
                LazyVGrid(columns: columns, spacing: 14) {
                    ForEach(shown) { p in card(p) }
                }
                .padding(20)
            }
        }
    }

    private func card(_ p: MWProject) -> some View {
        Button { open(p) } label: {
            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    Image(systemName: p.icon ?? "folder").font(.system(size: 16)).foregroundColor(appState.themeAccent)
                    Spacer()
                    if p.isPinned ?? false {
                        Image(systemName: "pin.fill").font(.system(size: 9)).foregroundColor(appState.themeTextSecondary)
                    }
                    Text((p.projectType ?? "general").capitalized)
                        .font(.system(size: 8, weight: .bold)).tracking(0.5).foregroundColor(appState.themeTextSecondary)
                        .padding(.horizontal, 6).padding(.vertical, 2)
                        .background(Capsule().fill(appState.themeAccent.opacity(0.10)))
                }
                Text(p.title).font(.system(size: 14, weight: .semibold)).foregroundColor(appState.themeText).lineLimit(2)
                    .frame(maxWidth: .infinity, alignment: .leading)
                Spacer(minLength: 0)
            }
            .padding(14).frame(height: 108, alignment: .top)
            .background(RoundedRectangle(cornerRadius: 10).fill(appState.themeCard))
            .overlay(RoundedRectangle(cornerRadius: 10).stroke(appState.themeBorder, lineWidth: 1))
        }
        .buttonStyle(.plain)
        .contextMenu {
            Button(p.isPinned ?? false ? "Unpin" : "Pin") { Task { await togglePin(p) } }
            Divider()
            AuxOpenMenuButtons(target: .project(p.id))
            Divider()
            Button("Archive") { Task { await archive(p) } }
            Button("Delete…") { confirmDelete(p) }
        }
    }

    private func archive(_ p: MWProject) async {
        try? await MatchaWorkService.shared.archiveProject(id: p.id)
        await MainActor.run {
            if appState.selectedProjectId == p.id { appState.selectedProjectId = nil }
            appState.projectsListGeneration &+= 1
        }
        await load()
    }

    /// Permanent delete behind an explicit modal confirm — same pattern as the
    /// sidebar list's Delete… (project + sections + threads, irreversible).
    private func confirmDelete(_ p: MWProject) {
        let alert = NSAlert()
        alert.messageText = "Delete \"\(p.title)\"?"
        alert.informativeText = "Permanently deletes the project, its sections, and all associated threads and messages. Cannot be undone."
        alert.alertStyle = .critical
        alert.addButton(withTitle: "Delete Permanently")
        alert.addButton(withTitle: "Cancel")
        guard alert.runModal() == .alertFirstButtonReturn else { return }
        Task {
            try? await MatchaWorkService.shared.deleteProject(id: p.id)
            await MainActor.run {
                if appState.selectedProjectId == p.id { appState.selectedProjectId = nil }
                appState.projectsListGeneration &+= 1
            }
            await load()
        }
    }

    private func open(_ p: MWProject) {
        appState.selectedProjectId = p.id   // hub flag stays set → back returns here
        appState.selectedThreadId = nil; appState.selectedChannelId = nil
        appState.selectedJournalId = nil; appState.selectedEmailId = nil
    }

    private func create(type: String) {
        if type == "collab" {
            appState.collabProjectWizardMode = .create
            appState.showCollabProjectWizard = true
            return
        }
        Task {
            if let proj = try? await MatchaWorkService.shared.createProject(title: "New Project", projectType: type) {
                await MainActor.run { appState.projectsListGeneration &+= 1; open(proj) }
            }
        }
    }

    private func togglePin(_ p: MWProject) async {
        _ = try? await MatchaWorkService.shared.setProjectPinned(id: p.id, pinned: !(p.isPinned ?? false))
        await load()
    }

    private func load() async {
        let list = (try? await MatchaWorkService.shared.listProjects()) ?? projects
        await MainActor.run { projects = list; isLoading = false }
    }
}

// MARK: - Shared hub chrome (used by Projects / Threads / Channels hubs)

/// A pill used in hub filter bars. Selected = filled accent.
struct MWHubPill: View {
    let label: String
    let selected: Bool
    let action: () -> Void
    @Environment(AppState.self) private var appState
    var body: some View {
        Button(action: action) {
            Text(label).font(.system(size: 11, weight: selected ? .semibold : .regular))
                .foregroundColor(selected ? appState.themeOnAccent : appState.themeTextSecondary)
                .padding(.horizontal, 12).padding(.vertical, 5)
                .background(Capsule().fill(selected ? appState.themeAccent : appState.themeAccent.opacity(0.08)))
        }
        .buttonStyle(.plain)
    }
}

/// Rounded search field for hub headers.
struct MWHubSearch: View {
    @Binding var text: String
    @Environment(AppState.self) private var appState
    var body: some View {
        HStack(spacing: 6) {
            Image(systemName: "magnifyingglass").font(.system(size: 11)).foregroundColor(appState.themeTextSecondary)
            TextField("Search", text: $text).textFieldStyle(.plain)
                .font(.system(size: 12)).foregroundColor(appState.themeText).frame(width: 150)
        }
        .padding(.horizontal, 10).padding(.vertical, 6)
        .background(Capsule().fill(appState.themeText.opacity(0.06)))
    }
}

/// Persistent left rail for a hub: a small titled header + a scrollable list of
/// item rows. Stays mounted while a specific item is open in the right pane, so
/// the user can switch items / get back to the grid without losing context.
struct MWHubRail<Header: View, Rows: View>: View {
    @ViewBuilder var header: () -> Header
    @ViewBuilder var rows: () -> Rows
    @Environment(AppState.self) private var appState
    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header()
                .padding(.horizontal, 12).padding(.top, 12).padding(.bottom, 8)
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 1) { rows() }
                    .padding(.horizontal, 8).padding(.bottom, 12)
            }
        }
        .frame(maxHeight: .infinity, alignment: .top)
        .background(appState.themeSidebar.opacity(0.5))
    }
}

/// Collapsed form of a hub rail: a slim vertical strip with a single expand
/// control, handing the freed width to the detail pane. Shared by every hub
/// (Projects / Threads / Channels) and the Journals folder rail. Click to
/// restore the full rail.
struct MWHubRailStrip: View {
    let expand: () -> Void
    @Environment(AppState.self) private var appState
    var body: some View {
        VStack(spacing: 0) {
            Button(action: expand) {
                Image(systemName: "sidebar.left")
                    .font(.system(size: 13))
                    .foregroundColor(appState.themeTextSecondary)
                    .frame(width: 36, height: 40)
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .help("Show sidebar")
            Spacer(minLength: 0)
        }
        .frame(width: 36)
        .frame(maxHeight: .infinity, alignment: .top)
        .background(appState.themeSidebar.opacity(0.5))
    }
}

/// One row in a hub rail. `accent` tints the leading icon (star/pin); `selected`
/// fills the row. `trailing` is an optional small badge (unread count, status).
struct MWHubRailRow: View {
    let icon: String
    let title: String
    let selected: Bool
    var accent: Bool = false
    var trailing: String? = nil
    let action: () -> Void
    @Environment(AppState.self) private var appState
    var body: some View {
        Button(action: action) {
            HStack(spacing: 7) {
                Image(systemName: icon)
                    .font(.system(size: 11))
                    .foregroundColor(accent || selected ? appState.themeAccent : appState.themeTextSecondary)
                    .frame(width: 15)
                Text(title)
                    .font(.system(size: 12, weight: selected ? .semibold : .regular))
                    .foregroundColor(appState.themeText.opacity(0.92))
                    .lineLimit(1)
                Spacer(minLength: 4)
                if let trailing {
                    Text(trailing)
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundColor(appState.themeTextSecondary)
                }
            }
            .padding(.horizontal, 8).padding(.vertical, 5)
            .background(RoundedRectangle(cornerRadius: 6)
                .fill(selected ? appState.themeAccent.opacity(0.14) : Color.clear))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }
}

/// Small icon button used in hub rail headers (New / Browse).
struct MWHubRailIconButton: View {
    let icon: String
    let help: String
    let action: () -> Void
    @Environment(AppState.self) private var appState
    var body: some View {
        Button(action: action) {
            Image(systemName: icon).font(.system(size: 12))
                .foregroundColor(appState.themeTextSecondary)
        }
        .buttonStyle(.plain)
        .help(help)
    }
}

/// Centered empty-state with a single CTA, used by every hub.
struct MWHubEmpty: View {
    let icon: String
    let title: String
    let cta: String
    let action: () -> Void
    @Environment(AppState.self) private var appState
    var body: some View {
        VStack(spacing: 10) {
            Spacer()
            Image(systemName: icon).font(.system(size: 34)).foregroundColor(appState.themeTextSecondary)
            Text(title).font(.system(size: 14, weight: .medium)).foregroundColor(appState.themeText)
            Button(action: action) {
                Text(cta).font(.system(size: 12, weight: .semibold))
                    .padding(.horizontal, 14).padding(.vertical, 7)
                    .background(appState.themeAccent).foregroundColor(appState.themeOnAccent).cornerRadius(8)
            }
            .buttonStyle(.plain).padding(.top, 4)
            Spacer()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}
