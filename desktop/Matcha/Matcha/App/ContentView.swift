import SwiftUI
import AppKit

struct ContentView: View {
    @Environment(AppState.self) private var appState
    @State private var threadListVM = ThreadListViewModel()
    @State private var isCreating = false
    @State private var isOpeningCheckout = false
    @State private var upgradeError: String?
    @State private var showProfile = false
    @State private var sidebarTab: SidebarTab = .threads

    private struct GlassWindowModifier: ViewModifier {
        func body(content: Content) -> some View {
            if #available(macOS 15.0, *) {
                content.containerBackground(.ultraThinMaterial, for: .window)
            } else {
                content
            }
        }
    }

    enum SidebarTab: String, CaseIterable {
        case threads = "Threads"
        case projects = "Projects"
        case channels = "Channels"
        case people = "People"
        case inbox = "Inbox"
    }

    var body: some View {
        @Bindable var appState = appState

        NavigationSplitView {
            VStack(spacing: 0) {
                // Tab picker
                Picker("", selection: $sidebarTab) {
                    ForEach(SidebarTab.allCases, id: \.self) { tab in
                        HStack(spacing: 4) {
                            Text(tab.rawValue)
                            if tab == .inbox && appState.unreadInboxCount > 0 {
                                Text("\(appState.unreadInboxCount)")
                                    .font(.system(size: 9, weight: .bold))
                                    .foregroundColor(.white)
                                    .padding(.horizontal, 4)
                                    .background(Color.matcha500)
                                    .clipShape(Capsule())
                            }
                        }
                        .tag(tab)
                    }
                }
                .pickerStyle(.segmented)
                .padding(.horizontal, 8)
                .padding(.vertical, 6)

                switch sidebarTab {
                case .threads:
                    ThreadListView(viewModel: threadListVM)
                case .projects:
                    ProjectListView()
                case .channels:
                    ChannelsSidebarView()
                case .people:
                    VStack {
                        Spacer()
                        Text("people")
                            .font(.system(size: 11))
                            .foregroundColor(.white.opacity(0.4))
                        Text("connections & requests")
                            .font(.system(size: 10))
                            .foregroundColor(.white.opacity(0.3))
                        Spacer()
                    }
                    .frame(maxWidth: .infinity)
                    .background(.ultraThinMaterial)
                case .inbox:
                    InboxSidebarView()
                }
            }
            .navigationSplitViewColumnWidth(min: 240, ideal: 280, max: 360)
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
        .toolbar {
            ToolbarItem(placement: .status) {
                if let user = appState.currentUser {
                    HStack(spacing: 10) {
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
        .onChange(of: sidebarTab) {
            // Clear selections when switching tabs
            appState.showSkills = false
            switch sidebarTab {
            case .inbox:
                appState.selectedThreadId = nil
                appState.selectedProjectId = nil
                appState.selectedChannelId = nil
                appState.showPeople = false
                appState.showInbox = true
            case .people:
                appState.selectedThreadId = nil
                appState.selectedProjectId = nil
                appState.selectedChannelId = nil
                appState.showInbox = false
                appState.showPeople = true
            case .channels:
                appState.selectedThreadId = nil
                appState.selectedProjectId = nil
                appState.showInbox = false
                appState.showPeople = false
            case .threads, .projects:
                appState.selectedChannelId = nil
                appState.showInbox = false
                appState.showPeople = false
            }
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

// MARK: - Inbox Sidebar (lightweight conversation list for sidebar)

private struct InboxSidebarView: View {
    @Environment(AppState.self) private var appState
    @State private var conversations: [MWInboxConversation] = []
    @State private var isLoading = true

    var body: some View {
        VStack(spacing: 0) {
            if isLoading {
                Spacer()
                ProgressView().tint(.secondary)
                Spacer()
            } else if conversations.isEmpty {
                Spacer()
                VStack(spacing: 8) {
                    Image(systemName: "envelope").font(.system(size: 28)).foregroundColor(.secondary)
                    Text("No messages").font(.system(size: 13)).foregroundColor(.secondary)
                }
                Spacer()
            } else {
                List(conversations, id: \.id) { convo in
                    Button {
                        appState.showInbox = true
                        appState.selectedThreadId = nil
                        appState.selectedProjectId = nil
                    } label: {
                        HStack {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(convo.title ?? convo.participants?.first?.name ?? "Conversation")
                                    .font(.system(size: 12, weight: .medium))
                                    .foregroundColor(.white)
                                    .lineLimit(1)
                                if let preview = convo.lastMessagePreview {
                                    Text(preview)
                                        .font(.system(size: 10)).foregroundColor(.secondary).lineLimit(1)
                                }
                            }
                            Spacer()
                            if (convo.unreadCount ?? 0) > 0 {
                                Circle().fill(Color.matcha500).frame(width: 8, height: 8)
                            }
                        }
                    }
                    .buttonStyle(.plain)
                    .padding(.vertical, 2)
                }
                .listStyle(.sidebar)
                .scrollContentBackground(.hidden)
            }
        }
        .background(Color.appBackground)
        .task {
            do {
                let list = try await InboxService.shared.listConversations()
                await MainActor.run { conversations = list; isLoading = false }
            } catch {
                await MainActor.run { isLoading = false }
            }
        }
    }
}
