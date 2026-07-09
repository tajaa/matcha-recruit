import SwiftUI
import AppKit

// MARK: - Projects hub (full-pane dashboard)

/// Full-pane "Workspaces" home — opened by clicking the sidebar Workspaces nav row.
/// No persistent rail: browsing (grid, search, sort, multi-select bulk actions)
/// and working (a single open project's kanban/detail) are two distinct panes —
/// opening a project replaces the grid entirely; "‹ Projects" returns to it.
struct ProjectsLibraryView: View {
    @Environment(AppState.self) private var appState

    @State private var projects: [MWProject] = []
    @State private var isLoading = true
    @State private var search = ""
    @State private var filter: Filter = .all
    @State private var sort: Sort = .recent
    @State private var showTypePicker = false
    @State private var showNewBlog = false
    @State private var selectMode = false
    @State private var selectedIds: Set<String> = []
    @State private var confirmBulkDelete = false

    enum Filter: String, CaseIterable, Identifiable {
        case all = "All", pinned = "Pinned"
        var id: String { rawValue }
    }

    enum Sort: String, CaseIterable, Identifiable {
        case recent = "Recent", alpha = "A–Z"
        var id: String { rawValue }
    }

    private let columns = [GridItem(.adaptive(minimum: 200, maximum: 280), spacing: 14)]
    private let types: [(type: String, label: String, icon: String)] = [
        ("general", "General", "square.grid.2x2"),
        ("presentation", "Presentation", "rectangle.on.rectangle.angled"),
        ("recruiting", "Recruiting", "person.2"),
        ("collab", "Collab", "person.3.sequence"),
    ]

    var body: some View {
        Group {
            if let id = appState.selectedProjectId {
                VStack(spacing: 0) {
                    backBar
                    Divider().opacity(0.3)
                    ProjectDetailView(projectId: id)
                }
            } else {
                VStack(spacing: 0) {
                    header
                    Divider().background(appState.themeBorder)
                    content
                }
                .background(ThemeRadialBackground())
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .task { await load() }
        .onChange(of: appState.projectsListGeneration) { _, _ in Task { await load() } }
        .onChange(of: appState.selectedProjectId) { _, _ in
            selectMode = false; selectedIds.removeAll()
        }
        .confirmationDialog(
            "Delete \(selectedIds.count) project\(selectedIds.count == 1 ? "" : "s")?",
            isPresented: $confirmBulkDelete,
            titleVisibility: .visible
        ) {
            Button("Delete Permanently", role: .destructive) { Task { await bulkDelete() } }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("Permanently deletes each workspace, its sections, and all associated threads and messages. Cannot be undone.")
        }
        .sheet(isPresented: $showNewBlog) {
            NewBlogSheet { proj in
                appState.projectsListGeneration &+= 1
                open(proj)
            }
        }
    }

    // ── Back bar (shown while a project is open) ───────────────────────
    private var backBar: some View {
        HStack(spacing: 6) {
            Button { appState.selectedProjectId = nil } label: {
                HStack(spacing: 4) {
                    Image(systemName: "chevron.left").font(.system(size: 11, weight: .semibold))
                    Text("Workspaces").font(.system(size: 12, weight: .semibold))
                }
                .foregroundColor(appState.themeTextSecondary)
            }
            .buttonStyle(.plain)
            Spacer()
        }
        .padding(.horizontal, 14).padding(.vertical, 8)
    }

    private var typeMenu: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("New Workspace").font(.system(size: 12, weight: .semibold))
                .foregroundColor(appState.themeTextSecondary).padding(.bottom, 4)
            ForEach(types, id: \.type) { t in
                Button { showTypePicker = false; create(type: t.type) } label: {
                    HStack { Image(systemName: t.icon).frame(width: 16); Text(t.label).font(.system(size: 12)); Spacer() }
                        .padding(.vertical, 4).contentShape(Rectangle())
                }
                .buttonStyle(.plain).foregroundColor(appState.themeText)
            }
            Button { showTypePicker = false; showNewBlog = true } label: {
                HStack { Image(systemName: "doc.richtext").frame(width: 16); Text("Blog Post").font(.system(size: 12)); Spacer() }
                    .padding(.vertical, 4).contentShape(Rectangle())
            }
            .buttonStyle(.plain).foregroundColor(appState.themeText)
        }
        .padding(12).frame(width: 200)
    }

    private var shown: [MWProject] {
        var out = projects
        if filter == .pinned { out = out.filter { $0.isPinned ?? false } }
        if !search.isEmpty { out = out.filter { $0.title.localizedCaseInsensitiveContains(search) } }
        switch sort {
        case .alpha:
            out.sort { $0.title.localizedCaseInsensitiveCompare($1.title) == .orderedAscending }
        case .recent:
            out.sort { (parseMWDate($0.updatedAt ?? "") ?? .distantPast) > (parseMWDate($1.updatedAt ?? "") ?? .distantPast) }
        }
        return out.sorted { ($0.isPinned ?? false) && !($1.isPinned ?? false) }
    }

    private var header: some View {
        VStack(spacing: 12) {
            HStack(alignment: .center) {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Workspaces").font(.system(size: 20, weight: .bold)).foregroundColor(appState.themeText)
                    Text("Chat, boards, presentations, and files — one space per effort")
                        .font(.system(size: 12)).foregroundColor(appState.themeTextSecondary)
                }
                Spacer()
                if selectMode {
                    Button("Cancel") { selectMode = false; selectedIds.removeAll() }
                        .buttonStyle(.plain).foregroundColor(appState.themeTextSecondary)
                        .padding(.trailing, 4)
                } else {
                    Button { selectMode = true } label: {
                        Text("Select").font(.system(size: 12, weight: .medium))
                            .foregroundColor(appState.themeTextSecondary)
                    }
                    .buttonStyle(.plain).padding(.trailing, 4)
                    newButton
                }
            }
            if selectMode {
                bulkActionBar
            } else {
                HStack(spacing: 8) {
                    ForEach(Filter.allCases) { f in MWHubPill(label: f.rawValue, selected: filter == f) { filter = f } }
                    Divider().frame(height: 14)
                    ForEach(Sort.allCases) { s in MWHubPill(label: s.rawValue, selected: sort == s) { sort = s } }
                    Spacer()
                    MWHubSearch(text: $search)
                }
            }
        }
        .padding(20)
    }

    private var bulkActionBar: some View {
        HStack(spacing: 10) {
            Text("\(selectedIds.count) selected")
                .font(.system(size: 12, weight: .medium)).foregroundColor(appState.themeTextSecondary)
            Spacer()
            Button("Select All") { selectedIds = Set(shown.map(\.id)) }
                .buttonStyle(.plain).font(.system(size: 12)).foregroundColor(appState.themeAccent)
            Button("Archive Selected") { Task { await bulkArchive() } }
                .buttonStyle(.plain).font(.system(size: 12, weight: .medium))
                .foregroundColor(selectedIds.isEmpty ? appState.themeTextSecondary.opacity(0.5) : appState.themeText)
                .disabled(selectedIds.isEmpty)
            Button("Delete Selected") { confirmBulkDelete = true }
                .buttonStyle(.plain).font(.system(size: 12, weight: .medium))
                .foregroundColor(selectedIds.isEmpty ? .red.opacity(0.4) : .red)
                .disabled(selectedIds.isEmpty)
        }
    }

    private var newButton: some View {
        Button { showTypePicker = true } label: {
            HStack(spacing: 5) { Image(systemName: "plus"); Text("New Workspace").font(.system(size: 12, weight: .semibold)) }
                .padding(.horizontal, 12).padding(.vertical, 7)
                .background(appState.themeAccent).foregroundColor(appState.themeOnAccent).cornerRadius(8)
        }
        .buttonStyle(.plain)
        .popover(isPresented: $showTypePicker) { typeMenu }
    }

    @ViewBuilder private var content: some View {
        if isLoading {
            Spacer(); ProgressView().tint(appState.themeTextSecondary); Spacer()
        } else if shown.isEmpty {
            MWHubEmpty(icon: "square.grid.2x2",
                       title: search.isEmpty && filter == .all ? "No workspaces yet" : "Nothing here",
                       cta: "New Workspace") { showTypePicker = true }
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
        let isSelected = selectedIds.contains(p.id)
        return Button {
            if selectMode {
                if isSelected { selectedIds.remove(p.id) } else { selectedIds.insert(p.id) }
            } else {
                open(p)
            }
        } label: {
            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    if selectMode {
                        Image(systemName: isSelected ? "checkmark.circle.fill" : "circle")
                            .font(.system(size: 15))
                            .foregroundColor(isSelected ? appState.themeAccent : appState.themeTextSecondary.opacity(0.5))
                    } else {
                        Image(systemName: p.icon ?? "square.grid.2x2").font(.system(size: 16)).foregroundColor(appState.themeAccent)
                    }
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
            .overlay(RoundedRectangle(cornerRadius: 10).stroke(isSelected ? appState.themeAccent : appState.themeBorder, lineWidth: isSelected ? 2 : 1))
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

    private func bulkArchive() async {
        let ids = selectedIds
        await withTaskGroup(of: Void.self) { group in
            for id in ids { group.addTask { try? await MatchaWorkService.shared.archiveProject(id: id) } }
        }
        await MainActor.run {
            selectMode = false; selectedIds.removeAll()
            appState.projectsListGeneration &+= 1
        }
        await load()
    }

    private func bulkDelete() async {
        let ids = selectedIds
        await withTaskGroup(of: Void.self) { group in
            for id in ids { group.addTask { try? await MatchaWorkService.shared.deleteProject(id: id) } }
        }
        await MainActor.run {
            selectMode = false; selectedIds.removeAll()
            appState.projectsListGeneration &+= 1
        }
        await load()
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
            if let proj = try? await MatchaWorkService.shared.createProject(title: "New Workspace", projectType: type) {
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
