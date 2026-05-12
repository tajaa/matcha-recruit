import SwiftUI

/// Home dashboard. Surfaces active projects, in-flight blogs, open tasks, and
/// recent activity across the company so nothing falls through the cracks.
struct HomeDashboardView: View {
    @Environment(AppState.self) private var appState

    @State private var projects: [MWProject] = []
    @State private var openTasks: [MWOpenTask] = []
    @State private var activity: [MWActivityItem] = []
    @State private var isLoading = false
    @State private var errorMessage: String?
    @State private var isCreatingChat = false

    private var activeProjects: [MWProject] {
        projects
            .filter { ($0.projectType ?? "") != "blog" }
            .filter { ($0.status ?? "active") != "completed" }
            .sorted { ($0.updatedAt ?? "") > ($1.updatedAt ?? "") }
            .prefix(8)
            .map { $0 }
    }

    private var inFlightBlogs: [MWProject] {
        projects.filter { p in
            guard p.projectType == "blog" else { return false }
            let blogStatus = (p.projectData?["status"]?.value as? String) ?? "draft"
            return blogStatus != "published"
        }
        .sorted { ($0.updatedAt ?? "") > ($1.updatedAt ?? "") }
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                header
                quickActions
                if let err = errorMessage {
                    errorBanner(err)
                }
                HStack(alignment: .top, spacing: 14) {
                    activeProjectsCard
                        .frame(maxWidth: .infinity, alignment: .topLeading)
                    blogsCard
                        .frame(maxWidth: .infinity, alignment: .topLeading)
                }
                openTasksCard
                recentActivityCard
            }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .background(Color.appBackground)
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
                    ProgressView().controlSize(.small).tint(.white)
                } else {
                    Image(systemName: icon).font(.system(size: 11, weight: .medium))
                }
                Text(label).font(.system(size: 12, weight: .medium))
            }
            .foregroundColor(.white)
            .padding(.horizontal, 12)
            .padding(.vertical, 7)
            .background(Color.matcha600)
            .cornerRadius(6)
        }
        .buttonStyle(.plain)
        .disabled(isLoading)
        .keyboardShortcut("n", modifiers: .command)
    }

    // MARK: - Header

    private var header: some View {
        HStack(alignment: .center) {
            VStack(alignment: .leading, spacing: 2) {
                Text("Home")
                    .font(.system(size: 20, weight: .semibold))
                    .foregroundColor(.white)
                Text("What's in flight across your work.")
                    .font(.system(size: 11))
                    .foregroundColor(.white.opacity(0.5))
            }
            Spacer()
            Button { Task { await loadAll() } } label: {
                HStack(spacing: 4) {
                    if isLoading {
                        ProgressView().controlSize(.small).tint(.white)
                    } else {
                        Image(systemName: "arrow.clockwise").font(.system(size: 11))
                    }
                    Text("Refresh").font(.system(size: 11, weight: .medium))
                }
                .foregroundColor(.white)
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                .background(Color.matcha600)
                .cornerRadius(5)
            }
            .buttonStyle(.plain)
            .disabled(isLoading)
        }
    }

    // MARK: - Cards

    private var activeProjectsCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            cardHeader(title: "ACTIVE PROJECTS", trailing: activeProjects.isEmpty ? nil : "\(activeProjects.count)")
            if activeProjects.isEmpty {
                Text("No active projects yet.")
                    .font(.system(size: 11))
                    .foregroundColor(.white.opacity(0.4))
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
                                .foregroundColor(.matcha500)
                                .frame(width: 14)
                            Text(project.title)
                                .font(.system(size: 12))
                                .foregroundColor(.white.opacity(0.85))
                                .lineLimit(1)
                            Spacer()
                            if let updated = project.updatedAt, let date = parseMWDate(updated) {
                                Text(relativeTime(from: date))
                                    .font(.system(size: 9))
                                    .foregroundColor(.white.opacity(0.4))
                            }
                        }
                    }
                    .buttonStyle(.plain)
                    .padding(.vertical, 2)
                }
            }
        }
        .padding(12)
        .background(Color.zinc900.opacity(0.5))
        .cornerRadius(8)
    }

    private var blogsCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            cardHeader(title: "BLOGS IN FLIGHT", trailing: inFlightBlogs.isEmpty ? nil : "\(inFlightBlogs.count)")
            if inFlightBlogs.isEmpty {
                Text("No drafts. Spin one up from the sidebar.")
                    .font(.system(size: 11))
                    .foregroundColor(.white.opacity(0.4))
                    .padding(.vertical, 4)
            } else {
                ForEach(inFlightBlogs) { blog in
                    Button {
                        appState.selectedProjectId = blog.id
                        appState.selectedJournalId = nil
                        appState.showHome = false
                    } label: {
                        HStack(spacing: 8) {
                            Image(systemName: "doc.text")
                                .font(.system(size: 10))
                                .foregroundColor(.matcha500)
                                .frame(width: 14)
                            Text(blog.title)
                                .font(.system(size: 12))
                                .foregroundColor(.white.opacity(0.85))
                                .lineLimit(1)
                            Spacer()
                            blogStatusPill(for: blog)
                        }
                    }
                    .buttonStyle(.plain)
                    .padding(.vertical, 2)
                }
            }
        }
        .padding(12)
        .background(Color.zinc900.opacity(0.5))
        .cornerRadius(8)
    }

    private var openTasksCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            cardHeader(title: "OPEN TASKS", trailing: openTasks.isEmpty ? nil : "\(openTasks.count)")
            if openTasks.isEmpty {
                Text("No open tasks. Nice.")
                    .font(.system(size: 11))
                    .foregroundColor(.white.opacity(0.4))
                    .padding(.vertical, 4)
            } else {
                ForEach(openTasks) { task in
                    Button {
                        if let pid = task.projectId {
                            appState.selectedProjectId = pid
                            appState.selectedJournalId = nil
                            appState.showHome = false
                        }
                    } label: {
                        VStack(alignment: .leading, spacing: 3) {
                            HStack(spacing: 8) {
                                Circle().fill(priorityColor(task.priority)).frame(width: 6, height: 6)
                                Text(task.title)
                                    .font(.system(size: 12))
                                    .foregroundColor(.white.opacity(0.85))
                                    .lineLimit(1)
                                Spacer()
                                if let projectTitle = task.projectTitle {
                                    Text(projectTitle)
                                        .font(.system(size: 9, weight: .medium))
                                        .foregroundColor(.white.opacity(0.6))
                                        .padding(.horizontal, 6)
                                        .padding(.vertical, 2)
                                        .background(Color.zinc800)
                                        .cornerRadius(3)
                                }
                                if let due = task.dueDate, !due.isEmpty {
                                    Text(due.prefix(10))
                                        .font(.system(size: 9))
                                        .foregroundColor(.white.opacity(0.5))
                                }
                            }
                            if let note = task.progressNote,
                               !note.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                                Text(note)
                                    .font(.system(size: 10))
                                    .italic()
                                    .foregroundColor(.white.opacity(0.5))
                                    .lineLimit(1)
                                    .padding(.leading, 14)
                            }
                        }
                    }
                    .buttonStyle(.plain)
                    .padding(.vertical, 3)
                }
            }
        }
        .padding(12)
        .background(Color.zinc900.opacity(0.5))
        .cornerRadius(8)
    }

    private var recentActivityCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            cardHeader(title: "RECENT ACTIVITY", trailing: activity.isEmpty ? nil : "\(activity.count)")
            if activity.isEmpty {
                Text("No activity in the last 14 days.")
                    .font(.system(size: 11))
                    .foregroundColor(.white.opacity(0.4))
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
                        default:
                            break
                        }
                    } label: {
                        HStack(spacing: 8) {
                            Image(systemName: activityIcon(item.kind))
                                .font(.system(size: 10))
                                .foregroundColor(.matcha500)
                                .frame(width: 14)
                            Text(item.title)
                                .font(.system(size: 12))
                                .foregroundColor(.white.opacity(0.85))
                                .lineLimit(1)
                            Spacer()
                            Text(item.kind)
                                .font(.system(size: 9, weight: .medium))
                                .foregroundColor(.white.opacity(0.4))
                                .textCase(.uppercase)
                            if let updated = item.updatedAt, let date = parseMWDate(updated) {
                                Text(relativeTime(from: date))
                                    .font(.system(size: 9))
                                    .foregroundColor(.white.opacity(0.4))
                            }
                        }
                    }
                    .buttonStyle(.plain)
                    .padding(.vertical, 2)
                }
            }
        }
        .padding(12)
        .background(Color.zinc900.opacity(0.5))
        .cornerRadius(8)
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
                    .foregroundColor(.white.opacity(0.4))
                    .padding(.horizontal, 5)
                    .padding(.vertical, 1)
                    .background(Color.zinc800)
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
                .foregroundColor(.white.opacity(0.85))
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

    private func blogStatusPill(for blog: MWProject) -> some View {
        let status = (blog.projectData?["status"]?.value as? String) ?? "draft"
        let label = status.capitalized
        let color: Color = status == "scheduled" ? .matcha500 : .white.opacity(0.5)
        return Text(label)
            .font(.system(size: 9, weight: .medium))
            .foregroundColor(color)
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(Color.zinc800)
            .cornerRadius(3)
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

        // Run all three requests in parallel; surface only the first failure.
        async let projectsTask: [MWProject] = MatchaWorkService.shared.listProjects(forceRefresh: true)
        async let tasksTask: [MWOpenTask] = MatchaWorkService.shared.listOpenTasks()
        async let activityTask: [MWActivityItem] = MatchaWorkService.shared.listRecentActivity()

        do {
            let (p, t, a) = try await (projectsTask, tasksTask, activityTask)
            self.projects = p
            self.openTasks = t
            self.activity = a
        } catch {
            self.errorMessage = "Couldn't load dashboard: \(error.localizedDescription)"
        }
    }
}
