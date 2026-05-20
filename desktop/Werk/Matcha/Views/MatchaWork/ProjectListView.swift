import SwiftUI
import AppKit

struct ProjectListView: View {
    @Environment(AppState.self) private var appState
    var showHeader: Bool = true
    var searchText: String = ""

    @State private var projects: [MWProject] = []
    @State private var isLoading = true
    @State private var isCreating = false
    @State private var showTypePicker = false
    @State private var showNewBlog = false

    // Memoized groupings — recomputed only when `projects` changes, not on
    // every selection-driven body redraw.
    @State private var blogs: [MWProject] = []
    @State private var collabs: [MWProject] = []
    @State private var discipline: [MWProject] = []
    @State private var general: [MWProject] = []
    @State private var archivedProjects: [MWProject] = []

    @AppStorage("mw-sidebar-proj-blogs-open")      private var blogsOpen      = true
    @AppStorage("mw-sidebar-proj-collabs-open")    private var collabsOpen    = true
    @AppStorage("mw-sidebar-proj-discipline-open") private var disciplineOpen = true
    @AppStorage("mw-sidebar-proj-general-open")    private var generalOpen    = true
    @AppStorage("mw-sidebar-proj-archived-open")   private var archivedOpen   = false

    // MARK: - Grouping

    private func recomputeGroups() {
        let matchesSearch: (MWProject) -> Bool = { p in
            searchText.isEmpty || p.title.localizedCaseInsensitiveContains(searchText)
        }
        let active = projects.filter { $0.status != "archived" && matchesSearch($0) }
        blogs = active.filter { $0.projectType == "blog" }.pinnedFirst()
        collabs = active.filter {
            $0.projectType == "collab" || $0.collaboratorRole == "collaborator"
        }.pinnedFirst()
        discipline = active.filter { $0.projectType == "discipline" }.pinnedFirst()
        let excluded: Set<String> = ["blog", "collab", "discipline"]
        general = active.filter { p in
            let t = p.projectType ?? "general"
            return !excluded.contains(t) && p.collaboratorRole != "collaborator"
        }.pinnedFirst()
        archivedProjects = projects
            .filter { $0.status == "archived" && matchesSearch($0) }
            .sorted { ($0.updatedAt ?? "") > ($1.updatedAt ?? "") }
    }

    private var selectionBinding: Binding<String?> {
        Binding(
            get: { appState.selectedProjectId },
            set: {
                appState.selectedProjectId = $0
                appState.selectedThreadId = nil
                appState.selectedJournalId = nil
                appState.showSkills = false
            }
        )
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
            } else {
                VStack(spacing: 4) {
                    if !blogs.isEmpty {
                        VStack(spacing: 0) {
                            projectSectionHeader(title: "Blogs", icon: "doc.richtext", count: blogs.count, isExpanded: $blogsOpen)
                            if blogsOpen {
                                VStack(spacing: 0) {
                                    ForEach(blogs) { p in
                                        blogRow(p)
                                    }
                                }
                            }
                        }
                    }
                    if !collabs.isEmpty {
                        VStack(spacing: 0) {
                            projectSectionHeader(title: "Collabs", icon: "person.2", count: collabs.count, isExpanded: $collabsOpen)
                            if collabsOpen {
                                VStack(spacing: 0) {
                                    ForEach(collabs) { p in
                                        collabRow(p)
                                    }
                                }
                            }
                        }
                    }
                    if !discipline.isEmpty {
                        VStack(spacing: 0) {
                            projectSectionHeader(title: "Discipline", icon: "exclamationmark.shield", count: discipline.count, isExpanded: $disciplineOpen)
                            if disciplineOpen {
                                VStack(spacing: 0) {
                                    ForEach(discipline) { p in
                                        genericRow(p, subtitle: sectionSubtitle(p))
                                    }
                                }
                            }
                        }
                    }
                    if !general.isEmpty {
                        VStack(spacing: 0) {
                            projectSectionHeader(title: "Projects", icon: "folder", count: general.count, isExpanded: $generalOpen)
                            if generalOpen {
                                VStack(spacing: 0) {
                                    ForEach(general) { p in
                                        genericRow(p, subtitle: sectionSubtitle(p))
                                    }
                                }
                            }
                        }
                    }
                    if !archivedProjects.isEmpty {
                        VStack(spacing: 0) {
                            projectSectionHeader(title: "Archived", icon: "archivebox", count: archivedProjects.count, isExpanded: $archivedOpen)
                            if archivedOpen {
                                VStack(spacing: 0) {
                                    ForEach(archivedProjects) { p in
                                        archivedRow(p)
                                    }
                                }
                            }
                        }
                    }
                }
                .padding(.vertical, 4)
            }
        }
        .background(Color.clear)
        .task(id: appState.projectsListGeneration) { await load() }
        .onChange(of: searchText) { _, _ in
            recomputeGroups()
        }
        .onReceive(NotificationCenter.default.publisher(for: .mwProjectTitlePatched)) { note in
            guard let patch = note.object as? MWProjectTitlePatch else { return }
            if let i = projects.firstIndex(where: { $0.id == patch.id }) {
                projects[i].title = patch.title
                recomputeGroups()
            }
        }
        .onReceive(NotificationCenter.default.publisher(for: .mwProjectDataChanged)) { _ in
            MatchaWorkService.shared.invalidateProjectLists()
            Task { await load() }
        }
        .sheet(isPresented: $showNewBlog) {
            NewBlogSheet { proj in
                projects.insert(proj, at: 0)
                recomputeGroups()
                appState.selectedProjectId = proj.id
                appState.selectedThreadId = nil
                appState.selectedJournalId = nil
                appState.projectsListGeneration &+= 1
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

    // MARK: - Section header

    private func sectionHeader(_ label: String, icon: String, count: Int) -> some View {
        HStack(spacing: 4) {
            Image(systemName: icon)
                .font(.system(size: 9, weight: .medium))
                .foregroundColor(.secondary)
            Text(label)
                .font(.system(size: 10, weight: .semibold))
                .foregroundColor(.secondary)
            Spacer()
            Text("\(count)")
                .font(.system(size: 9, weight: .medium))
                .foregroundColor(.secondary.opacity(0.6))
        }
    }

    // MARK: - Row builders

    // MARK: - Helper Layouts

    private func projectRowWrapper<Content: View>(_ p: MWProject, @ViewBuilder content: () -> Content) -> some View {
        let selected = appState.selectedProjectId == p.id
        return Button {
            appState.selectedProjectId = p.id
            appState.selectedThreadId = nil
            appState.selectedJournalId = nil
            appState.selectedChannelId = nil
            appState.showInbox = false
            appState.showSkills = false
        } label: {
            content()
                .padding(.horizontal, 12)
                .padding(.vertical, 6)
                .sidebarRowStyle(isSelected: selected)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

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

    @ViewBuilder
    private func blogRow(_ p: MWProject) -> some View {
        let status = (p.projectData?["status"]?.value as? String) ?? "draft"
        let statusColor: Color = status == "published" ? .green : status == "scheduled" ? .orange : .secondary
        let wc = (p.projectData?["word_count"]?.value as? Int) ?? 0

        projectRowWrapper(p) {
            rowShell(p) {
                HStack(spacing: 4) {
                    Text(status)
                        .font(.system(size: 9, weight: .medium))
                        .foregroundColor(statusColor)
                        .padding(.horizontal, 4).padding(.vertical, 1)
                        .background(statusColor.opacity(0.12))
                        .cornerRadius(3)
                    if wc > 0 {
                        Text("\(wc) words")
                            .font(.system(size: 10))
                            .foregroundColor(.secondary)
                    }
                }
            }
        }
    }

    @ViewBuilder
    private func collabRow(_ p: MWProject) -> some View {
        projectRowWrapper(p) {
            rowShell(p) {
                HStack(spacing: 4) {
                    if p.collaboratorRole == "collaborator" {
                        Text("shared")
                            .font(.system(size: 9, weight: .medium))
                            .foregroundColor(.purple)
                            .padding(.horizontal, 4).padding(.vertical, 1)
                            .background(Color.purple.opacity(0.12))
                            .cornerRadius(3)
                    }
                    if let collabs = p.collaborators {
                        let others = collabs.filter { $0.userId != appState.currentUser?.id }
                        if !others.isEmpty {
                            CollaboratorRowSummary(others: others)
                        }
                    }
                }
            }
        }
    }

    @ViewBuilder
    private func genericRow(_ p: MWProject, subtitle: String) -> some View {
        projectRowWrapper(p) {
            rowShell(p) {
                Text(subtitle)
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
            }
        }
    }

    @ViewBuilder
    private func archivedRow(_ p: MWProject) -> some View {
        projectRowWrapper(p) {
            VStack(alignment: .leading, spacing: 3) {
                Text(p.title)
                    .font(.system(size: 13, weight: .medium))
                    .foregroundColor(.secondary)
                    .lineLimit(1)
                Text(sectionSubtitle(p))
                    .font(.system(size: 10))
                    .foregroundColor(.secondary.opacity(0.6))
            }
            .padding(.vertical, 2)
            .contextMenu {
                Button("Unarchive") {
                    Task {
                        try? await MatchaWorkService.shared.unarchiveProject(id: p.id)
                        await load()
                    }
                }
            }
        }
    }

    @ViewBuilder
    private func rowShell<Sub: View>(_ p: MWProject, @ViewBuilder subtitle: () -> Sub) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            HStack(spacing: 4) {
                if p.isPinned ?? false {
                    Image(systemName: "star.fill")
                        .font(.system(size: 9))
                        .foregroundColor(appState.themeAccent)
                }
                Text(p.title)
                    .font(.system(size: 13, weight: .medium))
                    .foregroundColor(appState.themeText)
                    .lineLimit(1)
                Spacer()
                Button {
                    Task { await togglePin(project: p) }
                } label: {
                    Image(systemName: (p.isPinned ?? false) ? "star.fill" : "star")
                        .font(.system(size: 11))
                        .foregroundColor((p.isPinned ?? false) ? appState.themeAccent : appState.themeTextSecondary)
                }
                .buttonStyle(.plain)
                .help((p.isPinned ?? false) ? "Unstar" : "Star")
            }
            subtitle()
        }
        .padding(.vertical, 2)
        .contextMenu {
            Button((p.isPinned ?? false) ? "Unstar" : "Star") {
                Task { await togglePin(project: p) }
            }
            Menu("Export") {
                Button("PDF") { Task { await exportProject(p, format: "pdf") } }
                Button("Markdown") { Task { await exportProject(p, format: "md") } }
                Button("DOCX") { Task { await exportProject(p, format: "docx") } }
            }
            Button("Archive") {
                Task {
                    try? await MatchaWorkService.shared.archiveProject(id: p.id)
                    await MainActor.run {
                        if appState.selectedProjectId == p.id { appState.selectedProjectId = nil }
                    }
                    await load()
                }
            }
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

    private func sectionSubtitle(_ p: MWProject) -> String {
        let s = p.sections?.count ?? 0
        let c = p.chatCount ?? 0
        return "\(s) section\(s == 1 ? "" : "s") · \(c) chat\(c == 1 ? "" : "s")"
    }

    // MARK: - Data

    private func load() async {
        do {
            let p = try await MatchaWorkService.shared.listProjects()
            let filtered = p
            await MainActor.run {
                projects = filtered
                recomputeGroups()
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
        // Optimistic — flip the local row first so the star updates within one
        // frame. Re-group so pinned items resort. On failure, revert in place
        // and surface a console log; full list refresh is overkill for a
        // single boolean.
        await MainActor.run {
            if let i = projects.firstIndex(where: { $0.id == project.id }) {
                projects[i].isPinned = nextPinned
                recomputeGroups()
            }
        }
        do {
            _ = try await MatchaWorkService.shared.setProjectPinned(id: project.id, pinned: nextPinned)
            await MainActor.run { appState.projectsListGeneration &+= 1 }
        } catch {
            await MainActor.run {
                if let i = projects.firstIndex(where: { $0.id == project.id }) {
                    projects[i].isPinned = !nextPinned
                    recomputeGroups()
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
                    recomputeGroups()
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
