import SwiftUI

struct ProjectsListView: View {
    private let isPreview: Bool
    private struct Destination: Hashable {
        let projectId: String
        let taskId: String?
    }
    @Environment(AppState.self) private var appState
    @State private var vm = ProjectsListViewModel()
    @State private var path: [Destination] = []
    @State private var filter: MobileProjectFilter = .all
    @State private var search = ""
    @State private var creating = false
    @State private var editing: MWProject?
    @State private var archiveTarget: MWProject?

    init(previewProjects: [MWProject]? = nil) {
        isPreview = previewProjects != nil
        let model = ProjectsListViewModel()
        model.projects = previewProjects ?? []
        _vm = State(initialValue: model)
    }

    private var visible: [MWProject] {
        MobileProjectRules.visibleProjects(vm.projects, filter: filter, query: search)
    }
    private var activeCount: Int {
        MobileProjectRules.visibleProjects(vm.projects, filter: .all, query: "").filter { $0.status != "completed" }.count
    }

    var body: some View {
        NavigationStack(path: $path) {
            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    introduction
                    if !vm.invites.isEmpty { invitations }
                    filters
                    HStack {
                        EspressoSectionHeading(title: filter == .archived ? "On the shelf" : "Your projects", detail: "\(visible.count) projects")
                        if vm.isLoading { ProgressView().controlSize(.small) }
                    }
                    if visible.isEmpty && !vm.isLoading {
                        EspressoEmptyState(title: search.isEmpty ? "Room for your next idea" : "No matches",
                            message: search.isEmpty ? "Create a space for your own work, or bring your people together." : "Try another project name.", symbol: "square.stack.3d.up")
                        if search.isEmpty && filter != .archived {
                            Button("Create a project", systemImage: "plus") { creating = true }
                                .buttonStyle(.borderedProminent).controlSize(.large).frame(maxWidth: .infinity)
                        }
                    }
                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 260), spacing: 16)], spacing: 16) {
                        ForEach(visible) { project in
                            NavigationLink(value: Destination(projectId: project.id, taskId: nil)) {
                                MobileProjectCard(project: project)
                            }.buttonStyle(EspressoPressStyle()).contextMenu { projectMenu(project) }
                        }
                    }
                }.padding(20).frame(maxWidth: 1100).frame(maxWidth: .infinity)
            }
            .espressoBackground()
            .refreshable { await vm.load() }
            .searchable(text: $search, prompt: "Find a project")
            .navigationTitle("Espresso").navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Menu {
                        Text(appState.currentUser?.email ?? "Your account")
                        if let plan = appState.entitlements?.plan { Text("Espresso \(plan.displayName)") }
                        Button("Sign out", role: .destructive) { appState.logout() }
                    } label: { Image(systemName: "cup.and.saucer.fill").foregroundStyle(EspressoStyle.accent) }
                    .accessibilityLabel("Account")
                }
                ToolbarItem(placement: .primaryAction) {
                    Button("New project", systemImage: "plus") { creating = true }
                }
            }
            .navigationDestination(for: Destination.self) {
                CollabProjectView(projectId: $0.projectId, initialTaskId: $0.taskId)
            }
            .sheet(isPresented: $creating) {
                MobileProjectEditor { project in
                    await vm.load()
                    path = [Destination(projectId: project.id, taskId: nil)]
                }
            }
            .sheet(item: $editing) { project in MobileProjectEditor(project: project) { _ in await vm.load() } }
            .confirmationDialog("Archive this project? You can restore it from Archived.", isPresented: Binding(
                get: { archiveTarget != nil }, set: { if !$0 { archiveTarget = nil } }
            ), titleVisibility: .visible) {
                if let project = archiveTarget {
                    Button("Archive project", role: .destructive) {
                        Task { await vm.mutate { try await MatchaWorkService.shared.archiveProject(id: project.id) } }
                    }
                }
            }
            .espressoError($vm.errorMessage)
            .task { if !isPreview { await vm.load(); consumePendingProject() } }
        }
        .onChange(of: appState.pendingProjectId) { _, _ in consumePendingProject() }
    }

    private var introduction: some View {
        VStack(alignment: .leading, spacing: 16) {
            Label("A LITTLE FOCUS, EVERY DAY", systemImage: "sun.max")
                .font(.caption2.weight(.semibold)).tracking(1.2).foregroundStyle(EspressoStyle.accent)
            Text("Good things,\nin the making.")
                .font(.largeTitle.weight(.bold)).tracking(-1.1)
                .foregroundStyle(.primary).fixedSize(horizontal: false, vertical: true)
            Label("\(activeCount) active \(activeCount == 1 ? "space" : "spaces") · Endless possibility", systemImage: "sparkle")
                .font(.subheadline).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }.padding(.horizontal, 4).padding(.top, 14).padding(.bottom, 6)
            .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var filters: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            EspressoGlassGroup {
                HStack(spacing: 10) {
                    ForEach(MobileProjectFilter.allCases) { option in
                        Button { filter = option } label: {
                            HStack(spacing: 6) {
                                if filter == option { Image(systemName: "checkmark").font(.caption.weight(.bold)).accessibilityHidden(true) }
                                Text(option.rawValue).font(.subheadline.weight(.semibold))
                            }.padding(.horizontal, 16).frame(minHeight: 44)
                                .espressoGlass(selected: filter == option)
                        }.buttonStyle(.plain).accessibilityAddTraits(filter == option ? .isSelected : [])
                    }
                }
            }.padding(.vertical, 6)
        }.scrollClipDisabled()
    }

    private var invitations: some View {
        VStack(alignment: .leading, spacing: 16) {
            EspressoSectionHeading(title: "You're invited", detail: "\(vm.invites.count)")
            ForEach(vm.invites) { invite in
                VStack(alignment: .leading, spacing: 12) {
                    Label(invite.projectTitle, systemImage: "envelope.open").font(.headline)
                    Text("From \(invite.invitedBy)").font(.subheadline).foregroundStyle(.secondary)
                    HStack {
                        Button("Join project") { Task { await vm.respond(to: invite, accept: true) } }.buttonStyle(.borderedProminent)
                        Button("Decline") { Task { await vm.respond(to: invite, accept: false) } }.buttonStyle(.bordered)
                    }.disabled(vm.isMutating)
                }.espressoCard()
            }
        }
    }

    @ViewBuilder private func projectMenu(_ project: MWProject) -> some View {
        Button(project.isPinned == true ? "Unpin" : "Pin project", systemImage: "pin") {
            Task { await vm.mutate { _ = try await MatchaWorkService.shared.setProjectPinned(id: project.id, pinned: project.isPinned != true) } }
        }
        if project.mobileIsOwner {
            Button("Edit project", systemImage: "pencil") { editing = project }
            if project.status == "archived" {
                Button("Restore project", systemImage: "arrow.uturn.backward") {
                    Task { await vm.mutate { try await MatchaWorkService.shared.unarchiveProject(id: project.id) } }
                }
            } else {
                Button("Archive", systemImage: "archivebox", role: .destructive) { archiveTarget = project }
            }
        }
    }

    private func consumePendingProject() {
        guard let projectId = appState.pendingProjectId else { return }
        path = [Destination(projectId: projectId, taskId: appState.pendingTaskId)]
        appState.pendingProjectId = nil; appState.pendingTaskId = nil
    }
}

struct MobileProjectCard: View {
    let project: MWProject
    private var together: Bool { project.projectType == "collab" }
    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            HStack {
                EspressoProjectGlyph(symbol: project.icon ?? "folder", color: together ? EspressoStyle.sage : EspressoStyle.accent)
                Spacer()
                if project.isPinned == true { Image(systemName: "pin.fill").font(.caption).foregroundStyle(.secondary) }
                EspressoBadge(text: together ? "Together" : "Solo", color: together ? EspressoStyle.sage : EspressoStyle.accent)
            }
            Text(project.title).font(.title2.weight(.semibold)).tracking(-0.45).foregroundStyle(.primary).multilineTextAlignment(.leading).lineLimit(3)
            HStack {
                Label(project.status == "archived" ? "Archived" : "Open workspace", systemImage: together ? "person.2" : "lock")
                    .font(.caption).foregroundStyle(.secondary)
                Spacer()
                Image(systemName: "arrow.up.right").font(.subheadline.weight(.medium)).foregroundStyle(.secondary).accessibilityHidden(true)
            }
        }.frame(maxWidth: .infinity, alignment: .leading).espressoCard()
    }
}
