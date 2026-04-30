import SwiftUI
import AppKit

struct ProjectListView: View {
    @Environment(AppState.self) private var appState
    var showHeader: Bool = true
    @State private var projects: [MWProject] = []
    @State private var isLoading = true
    @State private var isCreating = false
    @State private var showTypePicker = false
    @State private var showNewBlog = false

    var body: some View {
        VStack(spacing: 0) {
            if showHeader {
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
                    .popover(isPresented: $showTypePicker) {
                        VStack(alignment: .leading, spacing: 4) {
                            Text("New Project").font(.system(size: 12, weight: .semibold)).foregroundColor(.secondary)
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
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 10)

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
                List(projects, selection: Binding(
                    get: { appState.selectedProjectId },
                    set: {
                        appState.selectedProjectId = $0
                        appState.selectedThreadId = nil
                        appState.showSkills = false
                    }
                )) { project in
                    VStack(alignment: .leading, spacing: 3) {
                        HStack(spacing: 4) {
                            if project.isPinned ?? false {
                                Image(systemName: "star.fill")
                                    .font(.system(size: 9))
                                    .foregroundColor(.matcha500)
                            }
                            Text(project.title)
                                .font(.system(size: 13, weight: .medium))
                                .foregroundColor(.white)
                                .lineLimit(1)
                            Spacer()
                            Button {
                                Task { await togglePin(project: project) }
                            } label: {
                                Image(systemName: (project.isPinned ?? false) ? "star.fill" : "star")
                                    .font(.system(size: 11))
                                    .foregroundColor((project.isPinned ?? false) ? .matcha500 : .secondary)
                            }
                            .buttonStyle(.plain)
                            .help((project.isPinned ?? false) ? "Unstar" : "Star")
                        }
                        HStack(spacing: 4) {
                            if let type = project.projectType {
                                Text(type == "blog" ? "blog" : type)
                                    .font(.system(size: 9, weight: .medium))
                                    .foregroundColor(.matcha500)
                                    .padding(.horizontal, 4)
                                    .padding(.vertical, 1)
                                    .background(Color.matcha500.opacity(0.12))
                                    .cornerRadius(3)
                            }
                            if project.collaboratorRole == "collaborator" {
                                Text("Collab")
                                    .font(.system(size: 9, weight: .medium))
                                    .foregroundColor(.purple)
                                    .padding(.horizontal, 4)
                                    .padding(.vertical, 1)
                                    .background(Color.purple.opacity(0.12))
                                    .cornerRadius(3)
                            }
                            if project.projectType == "collab",
                               let collabs = project.collaborators {
                                let others = collabs.filter { $0.userId != appState.currentUser?.id }
                                if !others.isEmpty {
                                    CollaboratorRowSummary(others: others)
                                }
                            }
                            if project.projectType == "blog" {
                                let blogStatus = (project.projectData?["status"]?.value as? String) ?? "draft"
                                let statusColor: Color = blogStatus == "published" ? .green : blogStatus == "scheduled" ? .orange : .secondary
                                Text(blogStatus)
                                    .font(.system(size: 9, weight: .medium))
                                    .foregroundColor(statusColor)
                                    .padding(.horizontal, 4)
                                    .padding(.vertical, 1)
                                    .background(statusColor.opacity(0.12))
                                    .cornerRadius(3)
                                let wc = (project.projectData?["word_count"]?.value as? Int) ?? 0
                                if wc > 0 {
                                    Text("\(wc) words")
                                        .font(.system(size: 10))
                                        .foregroundColor(.secondary)
                                }
                            } else {
                                let sCount = project.sections?.count ?? 0
                                let cCount = project.chatCount ?? 0
                                Text("\(sCount) section\(sCount == 1 ? "" : "s") · \(cCount) chat\(cCount == 1 ? "" : "s")")
                                    .font(.system(size: 10))
                                    .foregroundColor(.secondary)
                            }
                        }
                    }
                    .padding(.vertical, 2)
                    .tag(project.id)
                    .contextMenu {
                        Button((project.isPinned ?? false) ? "Unstar" : "Star") {
                            Task { await togglePin(project: project) }
                        }
                        Button("Archive") {
                            Task {
                                try? await MatchaWorkService.shared.archiveProject(id: project.id)
                                await load()
                            }
                        }
                    }
                }
                .listStyle(.sidebar)
                .scrollContentBackground(.hidden)
            }
        }
        .background(Color.appBackground)
        .task(id: appState.projectsListGeneration) { await load() }
        .sheet(isPresented: $showNewBlog) {
            NewBlogSheet { proj in
                projects.insert(proj, at: 0)
                appState.selectedProjectId = proj.id
                appState.selectedThreadId = nil
                appState.projectsListGeneration &+= 1
            }
        }
    }

    private func load() async {
        do {
            let p = try await MatchaWorkService.shared.listProjects()
            // Filter out consultations (their own sidebar section), then sort
            // pinned projects above unpinned. Within each bucket the original
            // server order (created_at DESC) is preserved.
            let filtered = p.filter { $0.projectType != "consultation" }
            let sorted = filtered.enumerated().sorted { lhs, rhs in
                let lp = lhs.element.isPinned ?? false
                let rp = rhs.element.isPinned ?? false
                if lp != rp { return lp && !rp }
                return lhs.offset < rhs.offset
            }.map { $0.element }
            await MainActor.run { projects = sorted; isLoading = false }
        } catch {
            await MainActor.run { isLoading = false }
        }
    }

    private func togglePin(project: MWProject) async {
        let nextPinned = !(project.isPinned ?? false)
        do {
            _ = try await MatchaWorkService.shared.updateProjectMeta(id: project.id, isPinned: nextPinned)
            await load()
        } catch {
            // Best-effort; surface as a console log only
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
                    appState.projectsListGeneration &+= 1
                    isCreating = false
                }
            } catch {
                print("[ProjectListView] create failed: \(error)")
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

/// Inline collaborator summary on a collab project row in the sidebar: shows
/// the first name(s) of up to 2 collaborators with a "+N" suffix. Tooltip
/// lists the full set. Self is filtered out by the caller, so the user sees
/// "with Alice, Bob" rather than their own name.
struct CollaboratorRowSummary: View {
    let others: [MWProjectCollaborator]
    private let maxNames = 2

    private var displayText: String {
        let visible = Array(others.prefix(maxNames))
        let names = visible.map { firstName($0.name) }
        let overflow = others.count - visible.count
        let joined = names.joined(separator: ", ")
        if overflow > 0 {
            return "\(joined) +\(overflow)"
        }
        return joined
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
                .foregroundColor(.secondary)
            Text(displayText)
                .font(.system(size: 10))
                .foregroundColor(.secondary)
                .lineLimit(1)
        }
        .padding(.horizontal, 5)
        .padding(.vertical, 1)
        .background(Color.matcha500.opacity(0.08))
        .cornerRadius(3)
        .help(tooltip)
    }

    private func firstName(_ full: String) -> String {
        let parts = full.split(separator: " ")
        return parts.first.map(String.init) ?? full
    }
}
