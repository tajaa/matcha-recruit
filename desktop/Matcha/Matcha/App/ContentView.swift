import SwiftUI
import AppKit

struct ContentView: View {
    @Environment(AppState.self) private var appState
    @State private var threadListVM = ThreadListViewModel()
    @State private var isCreating = false
    @State private var isOpeningCheckout = false
    @State private var upgradeError: String?
    @State private var showProfile = false
    @AppStorage("mw-sidebar-channels-open") private var channelsSectionOpen = true
    @AppStorage("mw-sidebar-consultations-open") private var consultationsSectionOpen = false
    @AppStorage("mw-sidebar-projects-open") private var projectsSectionOpen = true
    @AppStorage("mw-sidebar-threads-open") private var threadsSectionOpen = true
    @State private var showNewConsultation = false
    @State private var showNewBlog = false
    @State private var pendingConnectionsCount = 0
    @State private var showCreateChannel = false
    @State private var showProjectTypePicker = false
    @State private var isCreatingProject = false
    @State private var projectCreateError: String?
    @State private var showNotifications = false

    private struct GlassWindowModifier: ViewModifier {
        func body(content: Content) -> some View {
            if #available(macOS 15.0, *) {
                content.containerBackground(.ultraThinMaterial, for: .window)
            } else {
                content
            }
        }
    }

    var body: some View {
        @Bindable var appState = appState

        NavigationSplitView {
            VStack(spacing: 0) {
                ScrollView {
                    VStack(spacing: 0) {
                        sidebarSection(
                            title: "Channels",
                            icon: "number",
                            isOpen: $channelsSectionOpen,
                            trailing: {
                                Button { showCreateChannel = true } label: {
                                    Image(systemName: "plus")
                                        .font(.system(size: 10, weight: .semibold))
                                        .foregroundColor(.secondary)
                                        .frame(width: 18, height: 18)
                                        .background(Color.zinc800)
                                        .cornerRadius(4)
                                }
                                .buttonStyle(.plain)
                                .help("New channel")
                            }
                        ) {
                            ChannelsSidebarView(showHeader: false)
                                .frame(height: 220)
                        }

                        Divider().opacity(0.2)

                        sidebarSection(
                            title: "Consultations",
                            icon: "person.crop.rectangle.stack",
                            isOpen: $consultationsSectionOpen,
                            trailing: {
                                Button { showNewConsultation = true } label: {
                                    Image(systemName: "plus")
                                        .font(.system(size: 10, weight: .semibold))
                                        .foregroundColor(.secondary)
                                        .frame(width: 18, height: 18)
                                        .background(Color.zinc800)
                                        .cornerRadius(4)
                                }
                                .buttonStyle(.plain)
                                .help("New consultation")
                            }
                        ) {
                            ConsultationListView(showHeader: false)
                                .frame(height: 240)
                        }

                        Divider().opacity(0.2)

                        sidebarSection(
                            title: "Projects",
                            icon: "folder",
                            isOpen: $projectsSectionOpen,
                            trailing: {
                                Button { showProjectTypePicker = true } label: {
                                    Image(systemName: "plus")
                                        .font(.system(size: 10, weight: .semibold))
                                        .foregroundColor(.secondary)
                                        .frame(width: 18, height: 18)
                                        .background(Color.zinc800)
                                        .cornerRadius(4)
                                }
                                .buttonStyle(.plain)
                                .help("New project")
                                .disabled(isCreatingProject)
                                .popover(isPresented: $showProjectTypePicker) {
                                    VStack(alignment: .leading, spacing: 4) {
                                        Text("New Project").font(.system(size: 12, weight: .semibold)).foregroundColor(.secondary)
                                            .padding(.bottom, 4)
                                        ForEach(["general", "presentation", "recruiting", "collab"], id: \.self) { type in
                                            Button {
                                                showProjectTypePicker = false
                                                createProject(type: type)
                                            } label: {
                                                HStack {
                                                    Image(systemName: iconForProjectType(type))
                                                        .font(.system(size: 11))
                                                        .frame(width: 16)
                                                    Text(labelForProjectType(type))
                                                        .font(.system(size: 12))
                                                }
                                                .frame(maxWidth: .infinity, alignment: .leading)
                                                .padding(.vertical, 4)
                                            }
                                            .buttonStyle(.plain)
                                            .foregroundColor(.white)
                                        }
                                        Button {
                                            showProjectTypePicker = false
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
                                .sheet(isPresented: $showNewBlog) {
                                    NewBlogSheet { proj in
                                        appState.selectedProjectId = proj.id
                                        appState.selectedThreadId = nil
                                        appState.projectsListGeneration &+= 1
                                    }
                                }
                            }
                        ) {
                            VStack(alignment: .leading, spacing: 0) {
                                if let err = projectCreateError {
                                    HStack(alignment: .top, spacing: 6) {
                                        Image(systemName: "exclamationmark.triangle.fill")
                                            .font(.system(size: 9))
                                            .foregroundColor(.red)
                                        Text(err)
                                            .font(.system(size: 10))
                                            .foregroundColor(.red)
                                            .lineLimit(3)
                                        Spacer()
                                        Button { projectCreateError = nil } label: {
                                            Image(systemName: "xmark")
                                                .font(.system(size: 8))
                                                .foregroundColor(.secondary)
                                        }
                                        .buttonStyle(.plain)
                                    }
                                    .padding(.horizontal, 10)
                                    .padding(.vertical, 6)
                                    .background(Color.red.opacity(0.1))
                                }
                                ProjectListView(showHeader: false)
                                    .frame(height: 220)
                            }
                        }

                        Divider().opacity(0.2)

                        sidebarSection(
                            title: "Threads",
                            icon: "bubble.left.and.bubble.right",
                            isOpen: $threadsSectionOpen,
                            trailing: {
                                Button {
                                    NotificationCenter.default.post(name: .mwCreateNewThread, object: nil)
                                } label: {
                                    Image(systemName: "plus")
                                        .font(.system(size: 10, weight: .semibold))
                                        .foregroundColor(.secondary)
                                        .frame(width: 18, height: 18)
                                        .background(Color.zinc800)
                                        .cornerRadius(4)
                                }
                                .buttonStyle(.plain)
                                .help("New thread")
                            }
                        ) {
                            ThreadListView(viewModel: threadListVM, showHeader: false)
                                .frame(height: 280)
                        }
                    }
                }

                Divider().opacity(0.3)

                // Footer — Inbox + People always-visible buttons with live badges
                HStack(spacing: 6) {
                    sidebarFooterButton(
                        icon: "envelope",
                        label: "Inbox",
                        badge: appState.unreadInboxCount,
                        isActive: appState.showInbox
                    ) {
                        appState.showInbox = true
                        appState.showPeople = false
                        appState.selectedThreadId = nil
                        appState.selectedProjectId = nil
                        appState.selectedChannelId = nil
                        appState.showSkills = false
                    }

                    sidebarFooterButton(
                        icon: "person.2",
                        label: "People",
                        badge: pendingConnectionsCount,
                        isActive: appState.showPeople
                    ) {
                        appState.showPeople = true
                        appState.showInbox = false
                        appState.selectedThreadId = nil
                        appState.selectedProjectId = nil
                        appState.selectedChannelId = nil
                        appState.showSkills = false
                    }
                }
                .padding(.horizontal, 8)
                .padding(.vertical, 8)
                .background(Color.appBackground.opacity(0.5))
            }
            .background(Color.appBackground)
            .navigationSplitViewColumnWidth(min: 260, ideal: 300, max: 380)
            .task {
                await refreshPendingConnections()
            }
        } detail: {
            if let threadId = appState.selectedThreadId {
                ThreadDetailView(threadId: threadId)
                    .onChange(of: threadId) { appState.showSkills = false }
            } else if let projectId = appState.selectedProjectId {
                ProjectDetailView(projectId: projectId)
            } else if let channelId = appState.selectedChannelId {
                ChannelDetailView(channelId: channelId)
            } else if appState.showInbox {
                InboxView()
            } else if appState.showPeople {
                PeopleView()
            } else if appState.showSkills {
                SkillsView()
            } else {
                ZStack {
                    Color.appBackground.ignoresSafeArea()
                    VStack(spacing: 16) {
                        Image(systemName: "bubble.left.and.bubble.right")
                            .font(.system(size: 48))
                            .foregroundColor(.secondary)
                        Text("No thread selected")
                            .foregroundColor(.secondary)
                        Button {
                            guard !isCreating else { return }
                            isCreating = true
                            let dateStr = Date().formatted(date: .abbreviated, time: .omitted)
                            Task {
                                if let thread = await threadListVM.createThread(
                                    title: "New Chat \(dateStr)",
                                    initialMessage: nil
                                ) {
                                    await MainActor.run {
                                        appState.selectedThreadId = thread.id
                                        appState.showSkills = false
                                    }
                                }
                                isCreating = false
                            }
                        } label: {
                            if isCreating {
                                ProgressView().controlSize(.small).tint(.white)
                            } else {
                                Label("New Chat", systemImage: "plus")
                                    .font(.system(size: 13, weight: .medium))
                            }
                        }
                        .buttonStyle(.borderedProminent)
                        .tint(Color.matcha600)
                        .keyboardShortcut("n", modifiers: .command)
                        .disabled(isCreating)
                    }
                }
            }
        }
        .environment(appState)
        .modifier(GlassWindowModifier())
        .sheet(isPresented: $showProfile) {
            ProfileSheet()
                .environment(appState)
        }
        .sheet(isPresented: $showCreateChannel) {
            CreateChannelSheet { newChannel in
                appState.selectedThreadId = nil
                appState.selectedProjectId = nil
                appState.channelsListGeneration &+= 1
                NotificationCenter.default.post(name: .mwChannelCreated, object: newChannel.id)
            }
        }
        .sheet(isPresented: $showNewConsultation) {
            NewConsultationSheet { created in
                appState.selectedProjectId = created.id
                appState.selectedThreadId = nil
                appState.channelsListGeneration &+= 1
            }
        }
        .toolbar {
            ToolbarItem(placement: .status) {
                if let user = appState.currentUser {
                    HStack(spacing: 10) {
                        Button {
                            showNotifications.toggle()
                        } label: {
                            ZStack(alignment: .topTrailing) {
                                Image(systemName: "bell")
                                    .font(.system(size: 13))
                                    .foregroundColor(.white.opacity(0.7))
                                if appState.notificationsUnreadCount > 0 {
                                    Text(appState.notificationsUnreadCount > 9 ? "9+" : "\(appState.notificationsUnreadCount)")
                                        .font(.system(size: 8, weight: .bold))
                                        .foregroundColor(.white)
                                        .padding(.horizontal, 3)
                                        .padding(.vertical, 1)
                                        .background(Color.red)
                                        .clipShape(Capsule())
                                        .offset(x: 6, y: -5)
                                }
                            }
                            .frame(width: 22, height: 16)
                        }
                        .buttonStyle(.plain)
                        .help("Notifications")
                        .popover(isPresented: $showNotifications) {
                            NotificationsPopoverView()
                                .environment(appState)
                        }
                        Button {
                            showProfile = true
                        } label: {
                            Text(user.email)
                                .font(.system(size: 12))
                                .foregroundColor(.white.opacity(0.55))
                                .underline(false)
                        }
                        .buttonStyle(.plain)
                        .help("Edit profile")
                        if !appState.isPlusActive {
                            Button {
                                startUpgrade()
                            } label: {
                                Text(isOpeningCheckout ? "opening…" : "upgrade")
                                    .font(.system(size: 12, weight: .medium))
                                    .foregroundColor(upgradeError == nil ? Color.matcha500 : .red.opacity(0.8))
                            }
                            .buttonStyle(.plain)
                            .disabled(isOpeningCheckout)
                            .help(upgradeError ?? "Upgrade to Matcha Plus")
                        } else {
                            Text("plus")
                                .font(.system(size: 11))
                                .foregroundColor(Color.matcha500.opacity(0.8))
                        }
                        Button("logout") {
                            Task {
                                try? await AuthService.shared.logout()
                                await MainActor.run { appState.didLogout() }
                            }
                        }
                        .buttonStyle(.plain)
                        .font(.system(size: 12))
                        .foregroundColor(.white.opacity(0.5))
                    }
                }
            }
        }
    }

    // MARK: - Sidebar building blocks

    @ViewBuilder
    private func sidebarSection<Content: View, Trailing: View>(
        title: String,
        icon: String,
        isOpen: Binding<Bool>,
        @ViewBuilder trailing: () -> Trailing = { EmptyView() },
        @ViewBuilder content: () -> Content
    ) -> some View {
        VStack(spacing: 0) {
            HStack(spacing: 6) {
                Button {
                    withAnimation(.easeOut(duration: 0.15)) { isOpen.wrappedValue.toggle() }
                } label: {
                    HStack(spacing: 6) {
                        Image(systemName: isOpen.wrappedValue ? "chevron.down" : "chevron.right")
                            .font(.system(size: 9, weight: .semibold))
                            .foregroundColor(.secondary)
                            .frame(width: 10)
                        Image(systemName: icon)
                            .font(.system(size: 11))
                            .foregroundColor(.secondary)
                        Text(title.uppercased())
                            .font(.system(size: 10, weight: .semibold))
                            .foregroundColor(.secondary)
                            .tracking(0.5)
                        Spacer()
                    }
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)

                trailing()
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)

            if isOpen.wrappedValue {
                content()
            }
        }
    }

    @ViewBuilder
    private func sidebarFooterButton(
        icon: String,
        label: String,
        badge: Int,
        isActive: Bool,
        action: @escaping () -> Void
    ) -> some View {
        Button(action: action) {
            HStack(spacing: 6) {
                Image(systemName: icon)
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(isActive ? .white : .secondary)
                Text(label)
                    .font(.system(size: 12, weight: isActive ? .semibold : .regular))
                    .foregroundColor(isActive ? .white : .primary.opacity(0.85))
                if badge > 0 {
                    Text("\(badge)")
                        .font(.system(size: 9, weight: .bold))
                        .foregroundColor(.white)
                        .padding(.horizontal, 5)
                        .padding(.vertical, 1)
                        .background(Color.matcha500)
                        .clipShape(Capsule())
                }
                Spacer()
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .background(
                RoundedRectangle(cornerRadius: 6)
                    .fill(isActive ? Color.matcha500.opacity(0.8) : Color.zinc800.opacity(0.5))
            )
        }
        .buttonStyle(.plain)
    }

    private func refreshPendingConnections() async {
        do {
            let list = try await ChannelsService.shared.listPendingConnections()
            await MainActor.run { pendingConnectionsCount = list.count }
        } catch {
            // Silent failure — badge just won't update
        }
    }

    private func createProject(type: String) {
        isCreatingProject = true
        projectCreateError = nil
        Task {
            do {
                let proj = try await MatchaWorkService.shared.createProject(title: "New Project", projectType: type)
                await MainActor.run {
                    appState.selectedProjectId = proj.id
                    appState.selectedThreadId = nil
                    appState.selectedChannelId = nil
                    appState.projectsListGeneration &+= 1
                    isCreatingProject = false
                }
            } catch {
                await MainActor.run {
                    isCreatingProject = false
                    projectCreateError = "Couldn't create project: \(error.localizedDescription)"
                }
            }
        }
    }

    private func iconForProjectType(_ type: String) -> String {
        switch type {
        case "general": return "doc.text"
        case "presentation": return "rectangle.on.rectangle"
        case "recruiting": return "person.3"
        case "collab": return "person.2.crop.square.stack"
        default: return "doc.text"
        }
    }

    private func labelForProjectType(_ type: String) -> String {
        switch type {
        case "collab": return "Collab"
        default: return type.capitalized
        }
    }

    @MainActor
    private func startUpgrade() {
        guard !isOpeningCheckout else { return }
        isOpeningCheckout = true
        upgradeError = nil
        Task { @MainActor in
            defer { isOpeningCheckout = false }
            do {
                let urlString = try await MatchaWorkService.shared.startPersonalCheckout(
                    successUrl: "https://hey-matcha.com/work?upgraded=1",
                    cancelUrl: "https://hey-matcha.com/work?canceled=1"
                )
                guard let checkoutURL = URL(string: urlString) else {
                    upgradeError = "invalid checkout URL from server"
                    return
                }
                NSWorkspace.shared.open(checkoutURL)
                // Subscription refresh happens when the user returns to the app
                // via the scenePhase .active observer in MatchaApp.
            } catch {
                upgradeError = error.localizedDescription
            }
        }
    }
}

