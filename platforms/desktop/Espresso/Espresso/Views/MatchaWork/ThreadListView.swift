import SwiftUI

private let threadListOutputFormatter: DateFormatter = {
    let formatter = DateFormatter()
    formatter.dateStyle = .medium
    formatter.timeStyle = .none
    return formatter
}()

private func formatThreadDate(_ iso: String) -> String {
    guard let date = parseMWDate(iso) else { return iso }
    return threadListOutputFormatter.string(from: date)
}

struct ThreadListView: View {
    @Environment(AppState.self) private var appState
    @Environment(\.openWindow) private var openWindow
    @Bindable var viewModel: ThreadListViewModel
    var showHeader: Bool = true
    var searchText: String = ""
    @State private var isCreating = false
    @State private var threadToDelete: MWThread?
    @State private var showDeleteConfirm = false
    @State private var visibleCount = 3
    private let pageSize = 3

    private func isRecentlyActive(_ dateString: String?, days: Int = 7) -> Bool {
        guard let ds = dateString, let date = parseMWDate(ds) else { return true }
        return Date().timeIntervalSince(date) < Double(days) * 86_400
    }

    let filterOptions = [
        (label: "All", value: Optional<String>.none),
        (label: "Active", value: Optional<String>.some("active")),
        (label: "Finalized", value: Optional<String>.some("finalized"))
    ]

    var body: some View {
        @Bindable var appState = appState

        VStack(spacing: 0) {
            if showHeader {
                // Header
                HStack {
                    Text("Matcha Work")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundColor(appState.themeTextSecondary)

                    // Online users
                    if !appState.onlineUsers.isEmpty {
                        HStack(spacing: -4) {
                            ForEach(appState.onlineUsers.prefix(5)) { user in
                                Circle()
                                    .fill(appState.themeAccent)
                                    .frame(width: 18, height: 18)
                                    .overlay(
                                        Text(String(user.name.prefix(1)).uppercased())
                                            .font(.system(size: 8, weight: .bold))
                                            .foregroundColor(.white)
                                    )
                                    .overlay(
                                        Circle().stroke(appState.themeBg, lineWidth: 1.5)
                                    )
                                    .help(user.name)
                            }
                            if appState.onlineUsers.count > 5 {
                                Circle()
                                    .fill(appState.themeCard)
                                    .frame(width: 18, height: 18)
                                    .overlay(
                                        Text("+\(appState.onlineUsers.count - 5)")
                                            .font(.system(size: 7, weight: .bold))
                                            .foregroundColor(appState.themeTextSecondary)
                                    )
                                    .overlay(
                                        Circle().stroke(appState.themeBg, lineWidth: 1.5)
                                    )
                            }
                        }
                    }

                    Spacer()
                    Button {
                        createNewThread()
                    } label: {
                        if isCreating {
                            ProgressView()
                                .controlSize(.mini)
                                .frame(width: 24, height: 24)
                        } else {
                            Image(systemName: "plus")
                                .font(.system(size: 12, weight: .medium))
                                .foregroundColor(appState.themeTextSecondary)
                                .frame(width: 24, height: 24)
                                .background(appState.themeCard)
                                .cornerRadius(6)
                        }
                    }
                    .buttonStyle(.plain)
                    .disabled(isCreating)
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 10)

                Divider().background(appState.themeBorder)
            }

            // Thread list (filter lives in the section header menu)
            if viewModel.isLoading {
                ProgressView().tint(.secondary)
                    .frame(maxWidth: .infinity, alignment: .center)
                    .padding(.vertical, 12)
            } else if viewModel.filteredThreads.isEmpty {
                VStack(spacing: 8) {
                    Image(systemName: "bubble.left")
                        .font(.system(size: 28))
                        .foregroundColor(appState.themeTextSecondary)
                    Text("No threads yet")
                        .foregroundColor(appState.themeTextSecondary)
                        .font(.system(size: 11))
                }
                .frame(maxWidth: .infinity, alignment: .center)
                .padding(.vertical, 16)
            } else {
                let filtered = viewModel.filteredThreads
                    .filter { t in
                        // Apply 7-day recency filter on the "Active" tab only.
                        // "All", "Finalized", and "Archived" are intentional browses — no cutoff.
                        let passesRecency = viewModel.filterStatus != "active" || t.isPinned || isRecentlyActive(t.updatedAt)
                        let passesSearch = searchText.isEmpty || t.title.localizedCaseInsensitiveContains(searchText)
                        return passesRecency && passesSearch
                    }
                let limit = searchText.isEmpty ? visibleCount : filtered.count
                LazyVStack(spacing: 0) {
                    ForEach(filtered.prefix(limit), id: \.id) { thread in
                        let selected = appState.selectedThreadId == thread.id
                        Button {
                            appState.selectedThreadId = thread.id
                            appState.selectedProjectId = nil
                            appState.selectedChannelId = nil
                            appState.selectedJournalId = nil
                            appState.showInbox = false
                            appState.showPeople = false
                            appState.showHome = false
                            appState.showSkills = false
                        } label: {
                            ThreadRowView(
                                thread: thread,
                                isSelected: selected,
                                onDelete: {
                                    threadToDelete = thread
                                    showDeleteConfirm = true
                                },
                                onTogglePin: {
                                    Task { await viewModel.togglePin(thread: thread) }
                                }
                            )
                            .padding(.horizontal, 12)
                            .padding(.vertical, 6)
                            .sidebarRowStyle(isSelected: selected)
                            .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                        .contextMenu {
                            Button {
                                openWindow(id: "aux", value: AuxWindowTarget.thread(thread.id))
                            } label: {
                                Label("Open in new window", systemImage: "macwindow.on.rectangle")
                            }
                            Button {
                                appState.splitTarget = .thread(thread.id)
                            } label: {
                                Label("Open in split", systemImage: "rectangle.split.2x1")
                            }
                            Button {
                                appState.bottomSplitTarget = .thread(thread.id)
                            } label: {
                                Label("Open in bottom split", systemImage: "rectangle.split.1x2")
                            }
                            Divider()
                            Button(thread.isPinned ? "Unpin" : "Pin") {
                                Task { await viewModel.togglePin(thread: thread) }
                            }
                            if thread.status == "archived" {
                                Button("Unarchive") {
                                    Task { await viewModel.unarchiveThread(thread: thread) }
                                }
                            } else {
                                Button("Archive") {
                                    Task { await viewModel.archiveThread(thread: thread) }
                                }
                            }
                            Divider()
                            Button("Delete", role: .destructive) {
                                threadToDelete = thread
                                showDeleteConfirm = true
                            }
                        }
                    }
                    if searchText.isEmpty && filtered.count > visibleCount {
                        SidebarShowMoreButton(remaining: filtered.count - visibleCount, pageSize: pageSize) {
                            visibleCount += pageSize
                        }
                    }
                }
            }
        }
        .background(Color.clear)
        .safeAreaInset(edge: .bottom, spacing: 0) {
            VStack(spacing: 0) {
                Divider().background(appState.themeBorder.opacity(0.5))
                    .padding(.horizontal, 12)
                    .padding(.vertical, 4)
                Button {
                    appState.selectedThreadId = nil
                    appState.selectedProjectId = nil
                    appState.selectedChannelId = nil
                    appState.selectedJournalId = nil
                    appState.showInbox = false
                    appState.showPeople = false
                    appState.showHome = false
                    appState.showSkills = true
                } label: {
                    HStack(spacing: 8) {
                        Image(systemName: "bolt.fill")
                            .font(.system(size: 11))
                            .foregroundColor(appState.showSkills ? appState.themeAccent : appState.themeTextSecondary)
                            .frame(width: 16)
                        Text("Skills")
                            .font(.system(size: 12, weight: .medium))
                            .foregroundColor(appState.showSkills ? appState.themeText : appState.themeTextSecondary)
                        Spacer()
                    }
                    .padding(.horizontal, 12)
                    .padding(.vertical, 6)
                    .sidebarRowStyle(isSelected: appState.showSkills)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
            }
            .background(Color.clear)
        }
        .task { await viewModel.loadThreads() }
        .onReceive(NotificationCenter.default.publisher(for: .mwCreateNewThread)) { _ in
            createNewThread()
        }
        .confirmationDialog("Delete thread?", isPresented: $showDeleteConfirm) {
            Button("Delete", role: .destructive) {
                if let thread = threadToDelete {
                    if appState.selectedThreadId == thread.id {
                        appState.selectedThreadId = nil
                    }
                    Task { await viewModel.deleteThread(thread: thread) }
                }
            }
        } message: {
            Text("This cannot be undone.")
        }
    }

    private func createNewThread() {
        guard !isCreating else { return }
        isCreating = true
        let dateStr = Date().formatted(date: .abbreviated, time: .omitted)
        Task {
            if let thread = await viewModel.createThread(
                title: "New Chat \(dateStr)",
                initialMessage: nil
            ) {
                await MainActor.run {
                    appState.selectedThreadId = thread.id
                    appState.selectedProjectId = nil
                    appState.selectedChannelId = nil
                    appState.selectedJournalId = nil
                    appState.showSkills = false
                }
            }
            isCreating = false
        }
    }
}

extension Notification.Name {
    static let mwCreateNewThread = Notification.Name("mwCreateNewThread")
    static let mwThreadsChanged = Notification.Name("mwThreadsChanged")
    static let mwProjectDataChanged = Notification.Name("mwProjectDataChanged")
    /// Fires immediately on a project title rename so the sidebar can patch
    /// the row in place without waiting for the full project-list refetch
    /// kicked off by `mwProjectDataChanged`. Object is `MWProjectTitlePatch`.
    static let mwProjectTitlePatched = Notification.Name("mwProjectTitlePatched")
    /// Toolbar "browse" action posts this so ProjectFilesView opens the
    /// system file picker. Decoupled because the toolbar lives on the
    /// project view, not inside the files panel.
    static let mwCollabFilesBrowse = Notification.Name("mwCollabFilesBrowse")
}

struct MWProjectTitlePatch {
    let id: String
    let title: String
}

struct ThreadRowView: View {
    @Environment(AppState.self) private var appState
    let thread: MWThread
    var isSelected: Bool = false
    let onDelete: () -> Void
    var onTogglePin: (() -> Void)? = nil
    @State private var isHovered = false

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(alignment: .top) {
                // Per-type icon (chat → bubble, offer letter → doc, …).
                Image(systemName: thread.resolvedTaskType.icon)
                    .font(.system(size: 10))
                    .foregroundColor(appState.themeTextSecondary)
                    .frame(width: 14)
                if thread.isPinned {
                    Image(systemName: "star.fill")
                        .font(.system(size: 9))
                        .foregroundColor(appState.themeAccent)
                }
                Text(thread.displayName)
                    .font(.system(size: 13, weight: isSelected ? .bold : .regular))
                    .foregroundColor(appState.themeText)
                    .lineLimit(1)
                Spacer()
                if isHovered {
                    Button {
                        onTogglePin?()
                    } label: {
                        Image(systemName: thread.isPinned ? "star.fill" : "star")
                            .font(.system(size: 11))
                            .foregroundColor(thread.isPinned ? appState.themeAccent : appState.themeTextSecondary)
                    }
                    .buttonStyle(.plain)
                    .help(thread.isPinned ? "Unstar" : "Star")
                    Button(action: onDelete) {
                        Image(systemName: "trash")
                            .font(.system(size: 11))
                            .foregroundColor(appState.themeTextSecondary)
                    }
                    .buttonStyle(.plain)
                    .help("Delete")
                }
            }
            HStack(spacing: 4) {
                Text(thread.resolvedTaskType == .chat
                     ? formatThreadDate(thread.lastActivityAt)
                     : "\(thread.resolvedTaskType.label) · \(formatThreadDate(thread.lastActivityAt))")
                    .font(.system(size: 10))
                    .foregroundColor(appState.themeTextSecondary)
                    .lineLimit(1)
                if thread.nodeMode {
                    Text("Node")
                        .font(.system(size: 8, weight: .medium))
                        .foregroundColor(.purple)
                        .padding(.horizontal, 4)
                        .padding(.vertical, 1)
                        .background(Color.purple.opacity(0.15))
                        .cornerRadius(3)
                }
                if thread.complianceMode {
                    Text("Compliance")
                        .font(.system(size: 8, weight: .medium))
                        .foregroundColor(.cyan)
                        .padding(.horizontal, 4)
                        .padding(.vertical, 1)
                        .background(Color.cyan.opacity(0.15))
                        .cornerRadius(3)
                }
                if thread.payerMode {
                    Text("Payer")
                        .font(.system(size: 8, weight: .medium))
                        .foregroundColor(.green)
                        .padding(.horizontal, 4)
                        .padding(.vertical, 1)
                        .background(Color.green.opacity(0.15))
                        .cornerRadius(3)
                }
            }
        }
        .padding(.vertical, 2)
        .onHover { isHovered = $0 }
    }
}

// MARK: - Threads hub (full-pane dashboard)

/// Full-pane "Threads" hub — opened from the sidebar Threads nav row. Lists
/// every AI thread; filter (All / Active / Finalized), search, and create live
/// here. Picking a card sets `selectedThreadId` so the thread opens over the hub.
struct ThreadsLibraryView: View {
    @Environment(AppState.self) private var appState

    @State private var threads: [MWThread] = []
    @State private var isLoading = true
    @State private var search = ""
    @State private var filter: Filter = .all
    @State private var creating = false
    @State private var railSearch = ""
    @State private var railCollapsed = false

    enum Filter: String, CaseIterable, Identifiable {
        case all = "All", active = "Active", finalized = "Finalized"
        var id: String { rawValue }
        var status: String? { self == .all ? nil : (self == .active ? "active" : "finalized") }
    }

    private let columns = [GridItem(.adaptive(minimum: 220, maximum: 300), spacing: 14)]

    var body: some View {
        HSplitView {
            if railCollapsed {
                MWHubRailStrip { railCollapsed = false }
            } else {
                rail.frame(minWidth: 232, idealWidth: 258, maxWidth: 320)
            }
            Group {
                if let id = appState.selectedThreadId {
                    ThreadDetailView(threadId: id)
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
        .onChange(of: filter) { _, _ in Task { await load() } }
    }

    // ── Rail ────────────────────────────────────────────────────────────
    private var railThreads: [MWThread] {
        let base = railSearch.isEmpty ? threads : threads.filter { $0.displayName.localizedCaseInsensitiveContains(railSearch) }
        return base.sorted { ($0.isPinned ? 1 : 0, $0.lastActivityAt) > ($1.isPinned ? 1 : 0, $1.lastActivityAt) }
    }

    private var rail: some View {
        MWHubRail {
            VStack(spacing: 8) {
                HStack {
                    Text("Threads").font(.system(size: 12, weight: .semibold)).foregroundColor(appState.themeTextSecondary)
                    Spacer()
                    MWHubRailIconButton(icon: "sidebar.left", help: "Hide sidebar") { railCollapsed = true }
                    if creating { ProgressView().controlSize(.small) }
                    else { MWHubRailIconButton(icon: "plus", help: "New thread") { Task { await create() } } }
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
            MWHubRailRow(icon: "square.grid.2x2", title: "All Threads",
                         selected: appState.selectedThreadId == nil) {
                appState.selectedThreadId = nil
            }
            ForEach(railThreads) { t in
                MWHubRailRow(icon: t.isPinned ? "pin.fill" : "bubble.left.and.bubble.right",
                             title: t.displayName,
                             selected: appState.selectedThreadId == t.id,
                             accent: t.isPinned) { open(t.id) }
                    .contextMenu {
                        AuxOpenMenuButtons(target: .thread(t.id))
                    }
            }
        }
    }

    private var shown: [MWThread] {
        let base = search.isEmpty ? threads : threads.filter { $0.displayName.localizedCaseInsensitiveContains(search) }
        return base.sorted { ($0.isPinned ? 1 : 0, $0.lastActivityAt) > ($1.isPinned ? 1 : 0, $1.lastActivityAt) }
    }

    private var header: some View {
        VStack(spacing: 12) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Threads").font(.system(size: 20, weight: .bold)).foregroundColor(appState.themeText)
                    Text("Your AI chats and working sessions")
                        .font(.system(size: 12)).foregroundColor(appState.themeTextSecondary)
                }
                Spacer()
                Button { Task { await create() } } label: {
                    HStack(spacing: 5) {
                        if creating { ProgressView().controlSize(.small) }
                        else { Image(systemName: "plus") }
                        Text("New Thread").font(.system(size: 12, weight: .semibold))
                    }
                    .padding(.horizontal, 12).padding(.vertical, 7)
                    .background(appState.themeAccent).foregroundColor(appState.themeOnAccent).cornerRadius(8)
                }
                .buttonStyle(.plain).disabled(creating)
            }
            HStack(spacing: 8) {
                ForEach(Filter.allCases) { f in MWHubPill(label: f.rawValue, selected: filter == f) { filter = f } }
                Spacer()
                MWHubSearch(text: $search)
            }
        }
        .padding(20)
    }

    @ViewBuilder private var content: some View {
        if isLoading {
            Spacer(); ProgressView().tint(appState.themeTextSecondary); Spacer()
        } else if shown.isEmpty {
            MWHubEmpty(icon: "bubble.left.and.bubble.right",
                       title: search.isEmpty ? "No threads yet" : "No matches",
                       cta: "New Thread") { Task { await create() } }
        } else {
            ScrollView {
                LazyVGrid(columns: columns, spacing: 14) {
                    ForEach(shown) { t in card(t) }
                }
                .padding(20)
            }
        }
    }

    private func card(_ t: MWThread) -> some View {
        Button { open(t.id) } label: {
            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    Image(systemName: "bubble.left.and.bubble.right").font(.system(size: 14)).foregroundColor(appState.themeAccent)
                    Spacer()
                    if t.isPinned { Image(systemName: "pin.fill").font(.system(size: 9)).foregroundColor(appState.themeTextSecondary) }
                    Text(t.status.capitalized)
                        .font(.system(size: 8, weight: .bold)).tracking(0.5).foregroundColor(appState.themeTextSecondary)
                        .padding(.horizontal, 6).padding(.vertical, 2)
                        .background(Capsule().fill(appState.themeAccent.opacity(0.10)))
                }
                Text(t.displayName).font(.system(size: 13, weight: .semibold)).foregroundColor(appState.themeText).lineLimit(2)
                    .frame(maxWidth: .infinity, alignment: .leading)
                Spacer(minLength: 0)
            }
            .padding(14).frame(height: 104, alignment: .top)
            .background(RoundedRectangle(cornerRadius: 10).fill(appState.themeCard))
            .overlay(RoundedRectangle(cornerRadius: 10).stroke(appState.themeBorder, lineWidth: 1))
        }
        .buttonStyle(.plain)
        .contextMenu {
            AuxOpenMenuButtons(target: .thread(t.id))
        }
    }

    private func open(_ id: String) {
        appState.selectedThreadId = id   // hub flag stays set → back returns here
        appState.selectedProjectId = nil; appState.selectedChannelId = nil
        appState.selectedJournalId = nil; appState.selectedEmailId = nil
    }

    private func create() async {
        creating = true
        defer { creating = false }
        if let t = try? await MatchaWorkService.shared.createThread(title: nil, initialMessage: nil) {
            await MainActor.run { open(t.id) }
        }
    }

    private func load() async {
        isLoading = true
        let list = (try? await MatchaWorkService.shared.listThreads(status: filter.status)) ?? []
        await MainActor.run { threads = list; isLoading = false }
    }
}
