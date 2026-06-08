import SwiftUI

/// Home dashboard. Leads with the user's own work ("Assigned to me" — tasks
/// and subtasks assigned to them), then a compact view of active projects and
/// recent activity. Not-recently-active items tuck behind a disclosure.
struct HomeDashboardView: View {
    @Environment(AppState.self) private var appState

    @State private var projects: [MWProject] = []
    @State private var threads: [MWThread] = []
    @State private var journals: [MWJournal] = []
    @State private var channels: [ChannelSummary] = []
    @State private var openTasks: [MWOpenTask] = []
    @State private var activity: [MWActivityItem] = []
    @State private var isLoading = false
    @State private var errorMessage: String?
    @State private var isCreatingChat = false
    @State private var showOlder = false
    @State private var search = ""

    private func isRecentlyActive(_ dateString: String?, days: Int = 7) -> Bool {
        guard let ds = dateString, let date = parseMWDate(ds) else { return true }
        return Date().timeIntervalSince(date) < Double(days) * 86_400
    }

    private var activeProjects: [MWProject] {
        projects
            .filter { ($0.projectType ?? "") != "blog" }
            .filter { ($0.status ?? "active") != "completed" }
            .filter { isRecentlyActive($0.updatedAt) }
            .sorted { ($0.updatedAt ?? "") > ($1.updatedAt ?? "") }
            .prefix(8)
            .map { $0 }
    }

    private var olderProjects: [MWProject] {
        projects
            .filter { p in
                p.status != "archived" &&
                !(p.isPinned ?? false) &&
                !isRecentlyActive(p.updatedAt) &&
                (p.projectType ?? "") != "blog"
            }
            .sorted { ($0.updatedAt ?? "") > ($1.updatedAt ?? "") }
            .prefix(8)
            .map { $0 }
    }

    private var olderThreads: [MWThread] {
        threads
            .filter { t in
                t.status != "archived" &&
                !t.isPinned &&
                !isRecentlyActive(t.updatedAt)
            }
            .sorted { ($0.updatedAt ?? $0.createdAt) > ($1.updatedAt ?? $1.createdAt) }
            .prefix(8)
            .map { $0 }
    }

    private var olderJournals: [MWJournal] {
        journals
            .filter { !isRecentlyActive($0.updatedAt) }
            .sorted { ($0.updatedAt ?? "") > ($1.updatedAt ?? "") }
            .prefix(8).map { $0 }
    }

    private var olderChannels: [ChannelSummary] {
        let stars = ChannelStarStore.shared
        return channels
            .filter { !stars.isStarred($0.id) && !isRecentlyActive($0.lastMessageAt) }
            .sorted { ($0.lastMessageAt ?? "") > ($1.lastMessageAt ?? "") }
            .prefix(8).map { $0 }
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                searchHero
                if let err = errorMessage {
                    errorBanner(err)
                }
                if !trimmedSearch.isEmpty {
                    // Search mode: replace the dashboard with cross-surface hits.
                    searchResultsCard
                } else {
                    quickActions
                    // Lead with the user's own work, then a compact view of what's
                    // active. Blogs moved out; older items tuck behind a disclosure.
                    assignedToMeCard
                    activeProjectsCard
                    recentActivityCard
                    if !olderProjects.isEmpty || !olderThreads.isEmpty || !olderJournals.isEmpty || !olderChannels.isEmpty {
                        olderItemsDisclosure
                    }
                }
            }
            .padding(20)
            // Cap the reading width so cards don't stretch absurdly wide on a
            // big window (Linear/Things style), then center the capped block.
            .frame(maxWidth: 980)
            .frame(maxWidth: .infinity, alignment: .center)
        }
        .scrollContentBackground(.hidden)
        .background(ThemeRadialBackground())
        .onAppear { appState.setActiveContext(.home) }
        .task { await loadAll() }
    }

    private var quickActions: some View {
        HStack(spacing: 8) {
            quickActionButton(icon: "plus.bubble", label: "New Chat", isLoading: isCreatingChat) {
                guard !isCreatingChat else { return }
                isCreatingChat = true
                let dateStr = Date().formatted(date: .abbreviated, time: .omitted)
                Task {
                    do {
                        let thread = try await MatchaWorkService.shared.createThread(
                            title: "New Chat \(dateStr)",
                            initialMessage: nil
                        )
                        await MainActor.run {
                            appState.selectedThreadId = thread.id
                            appState.selectedJournalId = nil
                            appState.showHome = false
                            appState.showSkills = false
                            isCreatingChat = false
                        }
                    } catch {
                        await MainActor.run {
                            errorMessage = "Couldn't create chat: \(error.localizedDescription)"
                            isCreatingChat = false
                        }
                    }
                }
            }
            Spacer()
        }
    }

    private func quickActionButton(icon: String, label: String, isLoading: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 6) {
                if isLoading {
                    ProgressView().controlSize(.small).tint(appState.themeOnAccent)
                } else {
                    Image(systemName: icon).font(.system(size: 11, weight: .medium))
                }
                Text(label).font(.system(size: 12, weight: .medium))
            }
            .foregroundColor(appState.themeOnAccent)
            .padding(.horizontal, 12)
            .padding(.vertical, 7)
            .background(appState.themeAccent)
            .cornerRadius(6)
        }
        .buttonStyle(.plain)
        .disabled(isLoading)
        .keyboardShortcut("n", modifiers: .command)
    }

    // MARK: - Search hero

    private var trimmedSearch: String {
        search.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    /// First name (or capitalized email handle) for the greeting line.
    private var firstName: String {
        if let user = appState.currentUser {
            if let full = user.name,
               !full.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                return String(full.split(separator: " ").first ?? Substring(full))
            }
            if let handle = user.email.split(separator: "@").first {
                return String(handle).capitalized
            }
        }
        return "there"
    }

    private var searchHero: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .firstTextBaseline) {
                Text("What are we working on today, \(firstName)?")
                    .font(.system(size: 22, weight: .bold))
                    .foregroundColor(appState.themeText)
                Spacer(minLength: 8)
                Button { Task { await loadAll() } } label: {
                    if isLoading {
                        ProgressView().controlSize(.small).tint(appState.themeTextSecondary)
                    } else {
                        Image(systemName: "arrow.clockwise")
                            .font(.system(size: 12))
                            .foregroundColor(appState.themeTextSecondary)
                    }
                }
                .buttonStyle(.plain)
                .disabled(isLoading)
                .help("Refresh")
            }

            HStack(spacing: 9) {
                Image(systemName: "magnifyingglass")
                    .font(.system(size: 14))
                    .foregroundColor(appState.themeTextSecondary)
                TextField("Search projects, chats, threads, journals…", text: $search)
                    .textFieldStyle(.plain)
                    .font(.system(size: 15))
                    .foregroundColor(appState.themeText)
                if !search.isEmpty {
                    Button { search = "" } label: {
                        Image(systemName: "xmark.circle.fill")
                            .font(.system(size: 13))
                            .foregroundColor(appState.themeTextSecondary)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 11)
            .background(
                RoundedRectangle(cornerRadius: 10)
                    .fill(Color.cardBackground)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 10)
                    .stroke(appState.themeBorder, lineWidth: 1)
            )
        }
    }

    // MARK: - Cross-surface search

    private enum HitKind { case project, thread, journal, channel }

    private struct Hit: Identifiable {
        let id: String        // prefixed, unique across kinds
        let rawId: String     // entity id for navigation
        let kind: HitKind
        let title: String
    }

    private var hits: [Hit] {
        let q = trimmedSearch
        guard !q.isEmpty else { return [] }
        var out: [Hit] = []
        out += projects
            .filter { $0.title.localizedCaseInsensitiveContains(q) }
            .map { Hit(id: "p:\($0.id)", rawId: $0.id, kind: .project, title: $0.title) }
        out += threads
            .filter { $0.title.localizedCaseInsensitiveContains(q) }
            .map { Hit(id: "t:\($0.id)", rawId: $0.id, kind: .thread, title: $0.displayName) }
        out += journals
            .filter { $0.title.localizedCaseInsensitiveContains(q) }
            .map { Hit(id: "j:\($0.id)", rawId: $0.id, kind: .journal, title: $0.title) }
        out += channels
            .filter { $0.name.localizedCaseInsensitiveContains(q) }
            .map { Hit(id: "c:\($0.id)", rawId: $0.id, kind: .channel, title: $0.name) }
        return out
    }

    private func hitTypeLabel(_ k: HitKind) -> String {
        switch k {
        case .project: return "project"
        case .thread:  return "chat"
        case .journal: return "journal entry"
        case .channel: return "channel"
        }
    }

    private func hitIcon(_ k: HitKind) -> String {
        switch k {
        case .project: return "folder"
        case .thread:  return "bubble.left"
        case .journal: return "book.closed"
        case .channel: return "number"
        }
    }

    private func openHit(_ hit: Hit) {
        appState.selectedProjectId = nil
        appState.selectedThreadId = nil
        appState.selectedJournalId = nil
        appState.selectedChannelId = nil
        switch hit.kind {
        case .project: appState.selectedProjectId = hit.rawId
        case .thread:  appState.selectedThreadId = hit.rawId
        case .journal: appState.selectedJournalId = hit.rawId
        case .channel: appState.selectedChannelId = hit.rawId
        }
        appState.showHome = false
        search = ""
    }

    @ViewBuilder
    private var searchResultsCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            cardHeader(title: "RESULTS", trailing: hits.isEmpty ? nil : "\(hits.count)")
            if hits.isEmpty {
                Text("No matches for “\(trimmedSearch)”.")
                    .font(.system(size: 12))
                    .foregroundColor(appState.themeText.opacity(0.4))
                    .padding(.vertical, 6)
            } else {
                ForEach(hits) { hit in
                    Button { openHit(hit) } label: {
                        HStack(spacing: 9) {
                            Image(systemName: hitIcon(hit.kind))
                                .font(.system(size: 11))
                                .foregroundColor(appState.themeAccent)
                                .frame(width: 16)
                            Text(hit.title.isEmpty ? "Untitled" : hit.title)
                                .font(.system(size: 13))
                                .foregroundColor(appState.themeText.opacity(0.9))
                                .lineLimit(1)
                            Text("(\(hitTypeLabel(hit.kind)))")
                                .font(.system(size: 11))
                                .foregroundColor(appState.themeText.opacity(0.45))
                            Spacer(minLength: 0)
                        }
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .padding(.vertical, 3)
                }
            }
        }
        .padding(16)
        .elevatedCard(cornerRadius: 14)
    }

    // MARK: - Cards

    private var activeProjectsCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            cardHeader(title: "ACTIVE PROJECTS", trailing: activeProjects.isEmpty ? nil : "\(activeProjects.count)")
            if activeProjects.isEmpty {
                Text("No active projects yet.")
                    .font(.system(size: 11))
                    .foregroundColor(appState.themeText.opacity(0.4))
                    .padding(.vertical, 4)
            } else {
                ForEach(activeProjects) { project in
                    Button {
                        appState.selectedProjectId = project.id
                        appState.selectedJournalId = nil
                        appState.showHome = false
                    } label: {
                        HStack(spacing: 8) {
                            Image(systemName: projectIcon(project.projectType))
                                .font(.system(size: 10))
                                .foregroundColor(appState.themeAccent)
                                .frame(width: 14)
                            Text(project.title)
                                .font(.system(size: 12))
                                .foregroundColor(appState.themeText.opacity(0.85))
                                .lineLimit(1)
                            Spacer()
                            if let updated = project.updatedAt, let date = parseMWDate(updated) {
                                Text(relativeTime(from: date))
                                    .font(.system(size: 9))
                                    .foregroundColor(appState.themeText.opacity(0.4))
                            }
                        }
                    }
                    .buttonStyle(.plain)
                    .padding(.vertical, 2)
                }
            }
        }
        .padding(14)
        .elevatedCard(cornerRadius: 12)
    }

    /// Hero card: the current user's own open work — assigned top-level tasks
    /// plus assigned, not-yet-done subtasks (rendered indented with their
    /// parent task). Data comes from /tasks/open (strict assigned-to-me).
    private var assignedToMeCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            cardHeader(title: "ASSIGNED TO ME", trailing: openTasks.isEmpty ? nil : "\(openTasks.count)")
            if openTasks.isEmpty {
                Text("Nothing assigned to you right now.")
                    .font(.system(size: 12))
                    .foregroundColor(appState.themeText.opacity(0.4))
                    .padding(.vertical, 6)
            } else {
                ForEach(openTasks) { task in
                    Button {
                        if let pid = task.projectId {
                            appState.selectedProjectId = pid
                            appState.selectedJournalId = nil
                            appState.showHome = false
                        }
                    } label: {
                        assignedRow(task)
                    }
                    .buttonStyle(.plain)
                    .padding(.vertical, 3)
                }
            }
        }
        .padding(16)
        .elevatedCard(cornerRadius: 14)
    }

    @ViewBuilder
    private func assignedRow(_ task: MWOpenTask) -> some View {
        let isSub = task.isSubtask == true
        VStack(alignment: .leading, spacing: 3) {
            HStack(spacing: 8) {
                if isSub {
                    Image(systemName: "checklist")
                        .font(.system(size: 11))
                        .foregroundColor(appState.themeText.opacity(0.45))
                } else {
                    Circle().fill(priorityColor(task.priority)).frame(width: 6, height: 6)
                }
                Text(task.title)
                    .font(.system(size: 12, weight: isSub ? .regular : .medium))
                    .foregroundColor(appState.themeText.opacity(isSub ? 0.75 : 0.9))
                    .lineLimit(1)
                Spacer()
                if let projectTitle = task.projectTitle {
                    Text(projectTitle)
                        .font(.system(size: 9, weight: .medium))
                        .foregroundColor(appState.themeText.opacity(0.6))
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(Color.cardBackground)
                        .cornerRadius(3)
                }
                if let due = task.dueDate, !due.isEmpty {
                    Text(due.prefix(10))
                        .font(.system(size: 9))
                        .foregroundColor(appState.themeText.opacity(0.5))
                }
            }
            // Subtasks show their parent task; top-level tasks show progress.
            if isSub, let parent = task.parentTitle, !parent.isEmpty {
                Text("in: \(parent)")
                    .font(.system(size: 9))
                    .foregroundColor(appState.themeText.opacity(0.5))
                    .lineLimit(1)
                    .padding(.leading, 19)
            } else if !isSub, let note = task.progressNote,
                      !note.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                Text(note)
                    .font(.system(size: 10))
                    .italic()
                    .foregroundColor(appState.themeText.opacity(0.5))
                    .lineLimit(1)
                    .padding(.leading, 14)
            }
        }
        .padding(.leading, isSub ? 18 : 0)
        .contentShape(Rectangle())
    }

    /// "Show more" disclosure wrapping the not-recently-active items, collapsed
    /// by default to keep Home focused.
    private var olderItemsDisclosure: some View {
        DisclosureGroup(isExpanded: $showOlder) {
            olderItemsCard
                .padding(.top, 8)
        } label: {
            Text("Show more — not recently active")
                .font(.system(size: 11, weight: .medium))
                .foregroundColor(appState.themeText.opacity(0.6))
        }
        .padding(.horizontal, 4)
    }

    private var recentActivityCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            cardHeader(title: "RECENT ACTIVITY", trailing: activity.isEmpty ? nil : "\(activity.count)")
            if activity.isEmpty {
                Text("No activity in the last 14 days.")
                    .font(.system(size: 11))
                    .foregroundColor(appState.themeText.opacity(0.4))
                    .padding(.vertical, 4)
            } else {
                ForEach(activity) { item in
                    Button {
                        switch item.kind {
                        case "project":
                            appState.selectedProjectId = item.refId
                            appState.selectedJournalId = nil
                            appState.showHome = false
                        case "task":
                            if let pid = item.projectId {
                                appState.selectedProjectId = pid
                                appState.selectedJournalId = nil
                                appState.showHome = false
                            }
                        case "thread":
                            appState.selectedThreadId = item.refId
                            appState.selectedJournalId = nil
                            appState.showHome = false
                        case "journal":
                            appState.selectedJournalId = item.refId
                            appState.selectedProjectId = nil
                            appState.selectedThreadId = nil
                            appState.showHome = false
                        default:
                            break
                        }
                    } label: {
                        HStack(spacing: 8) {
                            Image(systemName: activityIcon(item.kind))
                                .font(.system(size: 10))
                                .foregroundColor(appState.themeAccent)
                                .frame(width: 14)
                            Text(item.title)
                                .font(.system(size: 12))
                                .foregroundColor(appState.themeText.opacity(0.85))
                                .lineLimit(1)
                            Spacer()
                            Text(item.kind)
                                .font(.system(size: 9, weight: .medium))
                                .foregroundColor(appState.themeText.opacity(0.4))
                                .textCase(.uppercase)
                            if let updated = item.updatedAt, let date = parseMWDate(updated) {
                                Text(relativeTime(from: date))
                                    .font(.system(size: 9))
                                    .foregroundColor(appState.themeText.opacity(0.4))
                            }
                        }
                    }
                    .buttonStyle(.plain)
                    .padding(.vertical, 2)
                }
            }
        }
        .padding(14)
        .elevatedCard(cornerRadius: 12)
    }

    private var olderItemsCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            cardHeader(title: "NOT RECENTLY ACTIVE", trailing: "\(olderProjects.count + olderThreads.count + olderJournals.count + olderChannels.count)")
            ForEach(olderProjects) { project in
                Button {
                    appState.selectedProjectId = project.id
                    appState.selectedJournalId = nil
                    appState.showHome = false
                } label: {
                    HStack(spacing: 8) {
                        Image(systemName: projectIcon(project.projectType))
                            .font(.system(size: 10))
                            .foregroundColor(appState.themeText.opacity(0.4))
                            .frame(width: 14)
                        Text(project.title)
                            .font(.system(size: 12))
                            .foregroundColor(appState.themeText.opacity(0.6))
                            .lineLimit(1)
                        Spacer()
                        if let updated = project.updatedAt, let date = parseMWDate(updated) {
                            Text(relativeTime(from: date))
                                .font(.system(size: 9))
                                .foregroundColor(appState.themeText.opacity(0.3))
                        }
                    }
                }
                .buttonStyle(.plain)
                .padding(.vertical, 2)
            }
            ForEach(olderThreads) { thread in
                Button {
                    appState.selectedThreadId = thread.id
                    appState.selectedJournalId = nil
                    appState.showHome = false
                } label: {
                    HStack(spacing: 8) {
                        Image(systemName: "bubble.left")
                            .font(.system(size: 10))
                            .foregroundColor(appState.themeText.opacity(0.4))
                            .frame(width: 14)
                        Text(thread.title)
                            .font(.system(size: 12))
                            .foregroundColor(appState.themeText.opacity(0.6))
                            .lineLimit(1)
                        Spacer()
                        if let updated = thread.updatedAt, let date = parseMWDate(updated) {
                            Text(relativeTime(from: date))
                                .font(.system(size: 9))
                                .foregroundColor(appState.themeText.opacity(0.3))
                        }
                    }
                }
                .buttonStyle(.plain)
                .padding(.vertical, 2)
            }
            ForEach(olderJournals) { j in
                Button {
                    appState.selectedJournalId = j.id
                    appState.selectedProjectId = nil
                    appState.selectedThreadId = nil
                    appState.selectedChannelId = nil
                    appState.showHome = false
                } label: {
                    HStack(spacing: 8) {
                        Image(systemName: j.icon ?? "book")
                            .font(.system(size: 10))
                            .foregroundColor(appState.themeText.opacity(0.4))
                            .frame(width: 14)
                        Text(j.title)
                            .font(.system(size: 12))
                            .foregroundColor(appState.themeText.opacity(0.6))
                            .lineLimit(1)
                        Spacer()
                        if let updated = j.updatedAt, let date = parseMWDate(updated) {
                            Text(relativeTime(from: date))
                                .font(.system(size: 9))
                                .foregroundColor(appState.themeText.opacity(0.3))
                        }
                    }
                }
                .buttonStyle(.plain)
                .padding(.vertical, 2)
            }
            ForEach(olderChannels, id: \.id) { ch in
                Button {
                    appState.selectedChannelId = ch.id
                    appState.selectedProjectId = nil
                    appState.selectedThreadId = nil
                    appState.selectedJournalId = nil
                    appState.showHome = false
                } label: {
                    HStack(spacing: 8) {
                        Image(systemName: "number")
                            .font(.system(size: 10))
                            .foregroundColor(appState.themeText.opacity(0.4))
                            .frame(width: 14)
                        Text(ch.name)
                            .font(.system(size: 12))
                            .foregroundColor(appState.themeText.opacity(0.6))
                            .lineLimit(1)
                        Spacer()
                        if let updated = ch.lastMessageAt, let date = parseMWDate(updated) {
                            Text(relativeTime(from: date))
                                .font(.system(size: 9))
                                .foregroundColor(appState.themeText.opacity(0.3))
                        }
                    }
                }
                .buttonStyle(.plain)
                .padding(.vertical, 2)
            }
        }
        .padding(14)
        .elevatedCard(cornerRadius: 12)
    }

    // MARK: - Helpers

    private func cardHeader(title: String, trailing: String?) -> some View {
        HStack {
            Text(title)
                .font(.system(size: 10, weight: .semibold))
                .foregroundColor(.secondary)
                .tracking(0.5)
            if let trailing {
                Text(trailing)
                    .font(.system(size: 9, weight: .medium))
                    .foregroundColor(appState.themeText.opacity(0.4))
                    .padding(.horizontal, 5)
                    .padding(.vertical, 1)
                    .background(Color.cardBackground)
                    .cornerRadius(3)
            }
            Spacer()
        }
    }

    private func errorBanner(_ msg: String) -> some View {
        HStack(spacing: 8) {
            Image(systemName: "exclamationmark.triangle.fill")
                .font(.system(size: 11))
                .foregroundColor(.red)
            Text(msg)
                .font(.system(size: 11))
                .foregroundColor(appState.themeText.opacity(0.85))
            Spacer()
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
        .background(Color.red.opacity(0.15))
        .cornerRadius(6)
    }

    private func projectIcon(_ type: String?) -> String {
        switch type {
        case "blog": return "doc.text"
        case "presentation": return "rectangle.stack"
        case "recruiting": return "person.2"
        case "collab": return "rectangle.split.3x1"
        case "discipline": return "shield"
        default: return "folder"
        }
    }

    private func activityIcon(_ kind: String) -> String {
        switch kind {
        case "project": return "folder.fill"
        case "task": return "checkmark.square"
        case "thread": return "bubble.left"
        case "journal": return "book"
        default: return "circle"
        }
    }

    private func priorityColor(_ priority: String) -> Color {
        switch priority {
        case "critical": return .red
        case "high": return .orange
        case "medium": return .yellow
        default: return .secondary
        }
    }

    private func relativeTime(from date: Date) -> String {
        let secs = Int(Date().timeIntervalSince(date))
        if secs < 60 { return "just now" }
        if secs < 3600 { return "\(secs/60)m" }
        if secs < 86400 { return "\(secs/3600)h" }
        return "\(secs/86400)d"
    }

    // MARK: - Loading

    private func loadAll() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        // All 6 start concurrently. Primary 4 are fatal; journals/channels are supplemental.
        async let projectsTask: [MWProject] = MatchaWorkService.shared.listProjects(forceRefresh: true)
        async let threadsTask: [MWThread] = MatchaWorkService.shared.listThreads(forceRefresh: true)
        async let tasksTask: [MWOpenTask] = MatchaWorkService.shared.listOpenTasks()
        async let activityTask: [MWActivityItem] = MatchaWorkService.shared.listRecentActivity()
        async let journalsTask: [MWJournal] = MatchaWorkService.shared.listJournals(forceRefresh: true)
        async let channelsTask: [ChannelSummary] = ChannelsService.shared.listChannels()

        do {
            let (p, th, t, a) = try await (projectsTask, threadsTask, tasksTask, activityTask)
            self.projects = p
            self.threads = th
            self.openTasks = t
            self.activity = a
        } catch {
            self.errorMessage = "Couldn't load dashboard: \(error.localizedDescription)"
        }
        self.journals = (try? await journalsTask) ?? []
        self.channels = (try? await channelsTask) ?? []
    }
}
