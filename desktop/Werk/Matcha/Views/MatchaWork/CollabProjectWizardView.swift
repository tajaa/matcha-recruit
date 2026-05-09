import SwiftUI

enum CollabProjectWizardMode: Equatable {
    case create
    case manage(projectId: String)

    var isManage: Bool {
        if case .manage = self { return true }
        return false
    }
}

/// 4-step guide for collab project owners. `.create` mode walks the user
/// through naming the project, inviting collaborators, and learning the
/// 5-panel layout. `.manage(projectId)` skips creation and shows the
/// current state as a refresher / re-invite surface.
struct CollabProjectWizardView: View {
    @Environment(\.dismiss) private var dismiss
    @Environment(AppState.self) private var appState

    let mode: CollabProjectWizardMode

    @AppStorage("collab-project-wizard-shown-v1") private var hasSeenWizard = false

    @State private var step: Int = 1

    // Step 2: create-mode form state
    @State private var title = ""
    @State private var description = ""
    @State private var creating = false
    @State private var createError: String?

    // Project loaded (.manage) or just-created (.create) — drives steps 3 & 4.
    @State private var project: MWProject?
    @State private var loadingProject = false
    @State private var loadError: String?

    @State private var inviteCount: Int = 0

    var body: some View {
        VStack(spacing: 0) {
            stepIndicator
            Divider().opacity(0.2)
            content
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            Divider().opacity(0.2)
            footer
        }
        .frame(width: 480, height: 540)
        .background(Color.appBackground)
        .task {
            if case .manage(let id) = mode {
                await loadExisting(id: id)
            }
        }
    }

    // MARK: - Step indicator

    private var stepIndicator: some View {
        HStack(spacing: 6) {
            ForEach(1...4, id: \.self) { i in
                Circle()
                    .fill(i <= step ? Color.matcha500 : Color.white.opacity(0.15))
                    .frame(width: 6, height: 6)
            }
            Spacer()
            Text("step \(step) of 4")
                .font(.system(size: 10))
                .foregroundColor(.white.opacity(0.4))
        }
        .padding(.horizontal, 18)
        .padding(.vertical, 10)
    }

    // MARK: - Content

    @ViewBuilder
    private var content: some View {
        switch step {
        case 1: welcomeStep
        case 2: configureStep
        case 3: inviteStep
        default: doneStep
        }
    }

    // MARK: - Step 1: welcome

    private var welcomeStep: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                Text(mode.isManage ? "managing your collab" : "starting a collab project")
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundColor(.white.opacity(0.95))
                Text(mode.isManage
                     ? "this guide reviews how the panels work and lets you re-invite collaborators."
                     : "collab projects bundle a kanban board, files, sections, and a real-time chat into one workspace. you become the owner.")
                    .font(.system(size: 12))
                    .foregroundColor(.white.opacity(0.6))
                    .fixedSize(horizontal: false, vertical: true)

                VStack(alignment: .leading, spacing: 10) {
                    capability(icon: "bubble.left.and.bubble.right", title: "chat", body: "a discussion channel auto-created with the project. chat is scoped to invited collaborators only.")
                    capability(icon: "rectangle.split.3x1", title: "kanban", body: "track tasks across todo / doing / done columns. drag-and-drop between lanes.")
                    capability(icon: "doc.on.doc", title: "files", body: "upload shared assets — pdf, images, video. previews inline. capped at 10mb / file.")
                    capability(icon: "list.bullet.rectangle", title: "sections", body: "long-form writing surface. ai chat can edit sections directly via directives.")
                    capability(icon: "person.2.crop.square.stack", title: "overview", body: "at-a-glance stats + collaborator list. invite from here too.")
                }
            }
            .padding(20)
        }
    }

    private func capability(icon: String, title: String, body: String) -> some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: icon)
                .font(.system(size: 13))
                .foregroundColor(Color.matcha500)
                .frame(width: 18)
                .padding(.top, 2)
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundColor(.white.opacity(0.85))
                Text(body)
                    .font(.system(size: 11))
                    .foregroundColor(.white.opacity(0.55))
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    // MARK: - Step 2: configure

    @ViewBuilder
    private var configureStep: some View {
        if mode.isManage {
            manageReview
        } else {
            createForm
        }
    }

    private var createForm: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                Text("name the project")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(.white.opacity(0.9))
                Text("collaborators see this in the sidebar and the project header. you can rename it anytime.")
                    .font(.system(size: 11))
                    .foregroundColor(.white.opacity(0.45))

                VStack(alignment: .leading, spacing: 4) {
                    Text("title").font(.system(size: 10)).foregroundColor(.white.opacity(0.4))
                    TextField("", text: $title, prompt: Text("q4 launch").foregroundColor(.white.opacity(0.25)))
                        .textFieldStyle(.plain)
                        .font(.system(size: 13))
                        .foregroundColor(.white.opacity(0.9))
                    Divider()
                }

                VStack(alignment: .leading, spacing: 4) {
                    Text("short description (optional)")
                        .font(.system(size: 10))
                        .foregroundColor(.white.opacity(0.4))
                    TextField("", text: $description, prompt: Text("what this project is about").foregroundColor(.white.opacity(0.25)), axis: .vertical)
                        .textFieldStyle(.plain)
                        .font(.system(size: 13))
                        .foregroundColor(.white.opacity(0.9))
                        .lineLimit(1...3)
                    Divider()
                    Text("description posts as the first message in the auto-created chat channel so collaborators know what they joined.")
                        .font(.system(size: 10))
                        .foregroundColor(.white.opacity(0.35))
                        .padding(.top, 2)
                }

                if let createError {
                    Text(createError)
                        .font(.system(size: 11))
                        .foregroundColor(.red.opacity(0.8))
                }
            }
            .padding(20)
        }
    }

    private var manageReview: some View {
        Group {
            if loadingProject {
                VStack { Spacer(); ProgressView(); Spacer() }
            } else if let project {
                ScrollView {
                    VStack(alignment: .leading, spacing: 14) {
                        Text(project.title)
                            .font(.system(size: 16, weight: .semibold))
                            .foregroundColor(.white.opacity(0.95))
                        configRow(label: "type", value: project.projectType ?? "collab")
                        configRow(label: "collaborators", value: "\(project.collaborators?.count ?? 0)")
                        if let role = project.collaboratorRole {
                            configRow(label: "your role", value: role)
                        }
                        Divider().opacity(0.2)
                        Text("editable from the project view")
                            .font(.system(size: 10))
                            .foregroundColor(.white.opacity(0.4))
                        Text("• click the title in the toolbar to rename\n• overview tab → invite to add people\n• kanban / files / sections live in the segmented picker at top")
                            .font(.system(size: 11))
                            .foregroundColor(.white.opacity(0.55))
                    }
                    .padding(20)
                }
            } else if let loadError {
                VStack {
                    Spacer()
                    Text(loadError)
                        .font(.system(size: 11))
                        .foregroundColor(.red.opacity(0.8))
                    Spacer()
                }
            }
        }
    }

    private func configRow(label: String, value: String) -> some View {
        HStack {
            Text(label)
                .font(.system(size: 11))
                .foregroundColor(.white.opacity(0.45))
            Spacer()
            Text(value)
                .font(.system(size: 12, weight: .medium))
                .foregroundColor(.white.opacity(0.85))
        }
    }

    // MARK: - Step 3: invite

    @ViewBuilder
    private var inviteStep: some View {
        if let project {
            VStack(spacing: 0) {
                Text("invite collaborators")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundColor(.white.opacity(0.9))
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal, 18)
                    .padding(.vertical, 10)
                Divider().opacity(0.2)
                CollabWizardInvitePicker(projectId: project.id) {
                    inviteCount += 1
                }
            }
        } else {
            VStack {
                Spacer()
                Text("no project loaded")
                    .font(.system(size: 11))
                    .foregroundColor(.white.opacity(0.45))
                Spacer()
            }
        }
    }

    // MARK: - Step 4: done

    private var doneStep: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                HStack(spacing: 8) {
                    Image(systemName: "checkmark.circle.fill")
                        .foregroundColor(Color.matcha500)
                        .font(.system(size: 18))
                    Text(mode.isManage ? "you're all set" : "project ready")
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundColor(.white.opacity(0.95))
                }
                if let project {
                    Text("\(project.title) · \((project.collaborators?.count ?? 0) + inviteCount) collaborator\(((project.collaborators?.count ?? 0) + inviteCount) == 1 ? "" : "s")")
                        .font(.system(size: 12))
                        .foregroundColor(.white.opacity(0.55))
                }
                Divider().opacity(0.2)
                Text("first moves")
                    .font(.system(size: 11, weight: .medium))
                    .foregroundColor(.white.opacity(0.55))
                bullet("post a kickoff message in chat — sets the tone for the channel")
                bullet("create your first kanban tasks so the team has something to grab")
                bullet("upload reference docs to files (10mb / file cap)")
                bullet("write the project brief in sections — collaborators can edit too")
            }
            .padding(20)
        }
    }

    private func bullet(_ text: String) -> some View {
        HStack(alignment: .top, spacing: 8) {
            Text("•")
                .foregroundColor(.white.opacity(0.4))
            Text(text)
                .font(.system(size: 11))
                .foregroundColor(.white.opacity(0.65))
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    // MARK: - Footer

    private var footer: some View {
        HStack {
            Button(skipLabel) {
                hasSeenWizard = true
                dismiss()
            }
            .buttonStyle(.plain)
            .font(.system(size: 12))
            .foregroundColor(.white.opacity(0.5))
            .keyboardShortcut(.escape, modifiers: [])

            Spacer()

            if step > 1 && step < 4 {
                Button("back") { step -= 1 }
                    .buttonStyle(.plain)
                    .font(.system(size: 12))
                    .foregroundColor(.white.opacity(0.6))
                    .padding(.horizontal, 6)
            }

            primaryButton
        }
        .padding(14)
    }

    private var skipLabel: String {
        switch step {
        case 1: return "skip wizard"
        case 4: return "close"
        default: return mode.isManage ? "close" : "skip"
        }
    }

    @ViewBuilder
    private var primaryButton: some View {
        switch step {
        case 1:
            Button("get started") { step = 2 }
                .buttonStyle(.borderedProminent)
                .tint(Color.matcha600)
                .controlSize(.small)
        case 2:
            if mode.isManage {
                Button("invite people") { step = 3 }
                    .buttonStyle(.borderedProminent)
                    .tint(Color.matcha600)
                    .controlSize(.small)
                    .disabled(project == nil)
            } else if project != nil {
                Button("invite people") { step = 3 }
                    .buttonStyle(.borderedProminent)
                    .tint(Color.matcha600)
                    .controlSize(.small)
            } else {
                Button {
                    Task { await create() }
                } label: {
                    if creating {
                        Text("creating…")
                    } else {
                        Text("create project")
                    }
                }
                .buttonStyle(.borderedProminent)
                .tint(Color.matcha600)
                .controlSize(.small)
                .disabled(creating || title.trimmingCharacters(in: .whitespaces).isEmpty)
                .keyboardShortcut(.return, modifiers: .command)
            }
        case 3:
            Button("next") { step = 4 }
                .buttonStyle(.borderedProminent)
                .tint(Color.matcha600)
                .controlSize(.small)
        default:
            Button("open project") {
                hasSeenWizard = true
                if let project {
                    appState.selectedProjectId = project.id
                    appState.selectedThreadId = nil
                    appState.selectedChannelId = nil
                    appState.showInbox = false
                    appState.showSkills = false
                }
                dismiss()
            }
            .buttonStyle(.borderedProminent)
            .tint(Color.matcha600)
            .controlSize(.small)
        }
    }

    // MARK: - Actions

    private func loadExisting(id: String) async {
        loadingProject = true
        defer { loadingProject = false }
        do {
            let proj = try await MatchaWorkService.shared.getProjectDetail(id: id)
            project = proj
        } catch {
            loadError = error.localizedDescription
        }
    }

    private func create() async {
        creating = true
        createError = nil
        defer { creating = false }
        let trimmed = title.trimmingCharacters(in: .whitespaces)
        do {
            let proj = try await MatchaWorkService.shared.createProject(
                title: trimmed,
                projectType: "collab"
            )
            project = proj
            appState.projectsListGeneration &+= 1
            step = 3
        } catch {
            createError = error.localizedDescription
        }
    }
}

/// Invite picker that drives addCollaborator one user at a time. Uses
/// MatchaWorkService.searchInvitableUsers (channels invitable-users API).
private struct CollabWizardInvitePicker: View {
    let projectId: String
    let onInvited: () -> Void

    @State private var query = ""
    @State private var users: [MWAdminSearchUser] = []
    @State private var loading = false
    @State private var error: String?
    @State private var addingIds: Set<String> = []
    @State private var addedIds: Set<String> = []
    @State private var searchTask: Task<Void, Never>?

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Image(systemName: "magnifyingglass")
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
                TextField("search by name or email", text: $query)
                    .textFieldStyle(.plain)
                    .font(.system(size: 12))
                    .foregroundColor(.white)
                    .onChange(of: query) { _, newValue in scheduleSearch(newValue) }
                if loading {
                    ProgressView().controlSize(.small)
                }
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 8)
            .background(Color.zinc800.opacity(0.4))

            Divider().opacity(0.2)

            if users.isEmpty && !loading {
                VStack(spacing: 8) {
                    Image(systemName: "person.crop.circle.badge.questionmark")
                        .font(.system(size: 22))
                        .foregroundColor(.secondary)
                    Text(query.isEmpty ? "type to search workspace people" : "no matching users")
                        .font(.system(size: 11))
                        .foregroundColor(.secondary)
                    Text("you can also skip this step and invite from the project overview later.")
                        .font(.system(size: 10))
                        .foregroundColor(.white.opacity(0.35))
                        .multilineTextAlignment(.center)
                        .padding(.horizontal, 30)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .padding(20)
            } else {
                ScrollView {
                    LazyVStack(spacing: 0) {
                        ForEach(users) { user in
                            row(user: user)
                            Divider().opacity(0.1)
                        }
                    }
                }
            }

            Divider().opacity(0.2)

            HStack {
                if let err = error {
                    Text(err).font(.system(size: 10)).foregroundColor(.red)
                }
                if !addedIds.isEmpty {
                    Text("added \(addedIds.count)")
                        .font(.system(size: 10))
                        .foregroundColor(Color.matcha500)
                }
                Spacer()
            }
            .padding(12)
        }
        .task { await search("") }
    }

    private func row(user: MWAdminSearchUser) -> some View {
        let added = addedIds.contains(user.id)
        let adding = addingIds.contains(user.id)
        return HStack(spacing: 10) {
            ZStack {
                Circle().fill(Color.matcha500.opacity(0.4)).frame(width: 26, height: 26)
                Text(String(user.name.prefix(1)).uppercased())
                    .font(.system(size: 11, weight: .bold))
                    .foregroundColor(.white)
            }
            VStack(alignment: .leading, spacing: 1) {
                Text(user.name).font(.system(size: 12)).foregroundColor(.white)
                Text(user.email).font(.system(size: 10)).foregroundColor(.secondary)
            }
            Spacer()
            if added {
                Label("added", systemImage: "checkmark")
                    .labelStyle(.titleAndIcon)
                    .font(.system(size: 10, weight: .medium))
                    .foregroundColor(Color.matcha500)
            } else if adding {
                ProgressView().controlSize(.small)
            } else {
                Button("add") {
                    Task { await add(user) }
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
                .tint(Color.matcha500)
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 7)
    }

    private func scheduleSearch(_ q: String) {
        searchTask?.cancel()
        searchTask = Task {
            try? await Task.sleep(for: .milliseconds(220))
            if Task.isCancelled { return }
            await search(q)
        }
    }

    private func search(_ q: String) async {
        loading = true
        defer { loading = false }
        do {
            users = try await MatchaWorkService.shared.searchInvitableUsers(query: q)
        } catch {
            self.error = error.localizedDescription
        }
    }

    private func add(_ user: MWAdminSearchUser) async {
        addingIds.insert(user.id)
        defer { addingIds.remove(user.id) }
        do {
            try await MatchaWorkService.shared.addCollaborator(projectId: projectId, userId: user.id)
            addedIds.insert(user.id)
            onInvited()
        } catch {
            self.error = error.localizedDescription
        }
    }
}
