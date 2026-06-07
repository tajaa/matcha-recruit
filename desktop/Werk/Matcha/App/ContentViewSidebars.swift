import SwiftUI

/// Root of a secondary (aux) window. Renders one surface, pinned to the target
/// passed via `openWindow(id:"aux", value:)`. Each detail view is `isEmbedded`
/// so it loads from the explicit id and never writes the main window's shared
/// nav/tab state. No sidebar — a focused single-surface window.
struct AuxWindowRootView: View {
    let target: AuxWindowTarget?
    @Environment(AppState.self) private var appState

    var body: some View {
        Group {
            if !appState.isAuthenticated {
                // macOS may restore an aux window on relaunch before sign-in;
                // don't render a detail view that would fire token-less requests.
                Text("Sign in to Werk to open this window.")
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
                case nil:
                    Text("Nothing to show")
                        .foregroundColor(.secondary)
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                }
            }
        }
        .frame(minWidth: 480, minHeight: 400)
        .background(appState.themeBg)
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
                        section("Projects", "folder") {
                            ForEach(projects) { p in
                                row(p.title, "folder",
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
        appState.selectedEmailId = nil
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

// MARK: - Sidebar "Starred" pins

/// The only place the sidebar surfaces specific items: a compact strip of
/// pinned projects + starred channels + pinned threads for quick access.
/// Everything else lives in the per-surface hubs. Tapping a pin opens that
/// item directly. Hidden entirely when nothing is pinned/starred.
struct SidebarStarredView: View {
    @Environment(AppState.self) private var appState
    @State private var pins: [Pin] = []

    struct Pin: Identifiable {
        let id: String
        let name: String
        let icon: String
        let kind: Kind
        enum Kind { case project, channel, thread, journal }
    }

    var body: some View {
        // Observe the client-side star stores so the strip reloads when a
        // channel/journal is (un)starred — those bump their OWN generation,
        // not the list generations.
        let _ = ChannelStarStore.shared.generation
        let _ = JournalStarStore.shared.generation
        return Group {
            if !pins.isEmpty {
                VStack(alignment: .leading, spacing: 1) {
                    Text("STARRED")
                        .font(.system(size: 9, weight: .semibold))
                        .tracking(0.5)
                        .foregroundColor(appState.themeTextSecondary)
                        .padding(.horizontal, 12)
                        .padding(.top, 6)
                        .padding(.bottom, 3)
                    ForEach(pins) { pin in row(pin) }
                    Divider().background(appState.themeBorder).padding(.top, 6)
                }
            }
        }
        .task { await load() }
        .onChange(of: appState.projectsListGeneration) { _, _ in Task { await load() } }
        .onChange(of: appState.channelsListGeneration) { _, _ in Task { await load() } }
        .onChange(of: appState.journalsListGeneration) { _, _ in Task { await load() } }
        .onChange(of: ChannelStarStore.shared.generation) { _, _ in Task { await load() } }
        .onChange(of: JournalStarStore.shared.generation) { _, _ in Task { await load() } }
    }

    private func row(_ pin: Pin) -> some View {
        let active = isActive(pin)
        return Button { open(pin) } label: {
            HStack(spacing: 8) {
                Image(systemName: pin.icon)
                    .font(.system(size: 11))
                    .foregroundColor(pin.kind == .channel ? appState.themeAccent : appState.themeTextSecondary)
                    .frame(width: 16)
                Text(pin.name)
                    .font(.system(size: 12, weight: active ? .semibold : .regular))
                    .foregroundColor(appState.themeText.opacity(0.9))
                    .lineLimit(1)
                Spacer(minLength: 0)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 5)
            .background(
                RoundedRectangle(cornerRadius: 6)
                    .fill(active ? appState.themeAccent.opacity(0.12) : Color.clear)
            )
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    private func isActive(_ pin: Pin) -> Bool {
        switch pin.kind {
        case .project: return appState.selectedProjectId == pin.id
        case .channel: return appState.selectedChannelId == pin.id
        case .thread:  return appState.selectedThreadId == pin.id
        case .journal: return appState.selectedJournalId == pin.id
        }
    }

    private func open(_ pin: Pin) {
        appState.clearPrimaryNav()
        switch pin.kind {
        case .project: appState.selectedProjectId = pin.id
        case .channel: appState.selectedChannelId = pin.id
        case .thread:  appState.selectedThreadId = pin.id
        case .journal: appState.selectedJournalId = pin.id
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
        var out: [Pin] = []
        out += projects.filter { $0.isPinned ?? false }
            .map { Pin(id: $0.id, name: $0.title, icon: $0.icon ?? "folder", kind: .project) }
        out += channels.filter { $0.isMember && cStars.isStarred($0.id) }
            .map { Pin(id: $0.id, name: $0.name, icon: "star.fill", kind: .channel) }
        out += journals.filter { jStars.isStarred($0.id) }
            .map { Pin(id: $0.id, name: $0.title, icon: $0.icon ?? "book.closed", kind: .journal) }
        out += threads.filter { $0.isPinned }
            .map { Pin(id: $0.id, name: $0.displayName, icon: "bubble.left.and.bubble.right", kind: .thread) }
        await MainActor.run { pins = out }
    }
}
