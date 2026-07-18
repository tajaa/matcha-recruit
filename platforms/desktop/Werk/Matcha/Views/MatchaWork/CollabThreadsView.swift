import SwiftUI
import AppKit

// MARK: - Collab Threads tab

/// AI chat threads scoped to a collab project. Private-per-person: you see
/// threads you created plus ones shared with you. Owner can share a thread with
/// other project collaborators. Chat only (no document preview) — reuses
/// `ChatPanelView`, so the project stays the active tab (unlike the standalone
/// `ThreadDetailView`, which would reassign the active context).
struct CollabThreadsView: View {
    let projectId: String
    let collaborators: [MWProjectCollaborator]
    let currentUserId: String?
    let lightMode: Bool
    let selectedModel: String?

    @Environment(AppState.self) private var appState
    @State private var threads: [MWThread] = []
    @State private var isLoading = false
    @State private var errorMessage: String?
    @State private var selectedThreadId: String?
    @State private var threadVM = ThreadDetailViewModel()
    @State private var creating = false
    /// User explicitly tapped "Threads" (back) to browse the list. Distinguishes
    /// an intentional list browse from the initial auto-open, so the back button
    /// can escape the auto-opened chat instead of immediately re-entering it.
    @State private var showList = false
    @State private var didAutoOpen = false

    private let service = MatchaWorkService.shared

    var body: some View {
        Group {
            if showList {
                threadList
            } else if let id = selectedThreadId {
                threadDetail(id: id)
            } else {
                // Entering the tab → drop straight into a ready chat (greeting +
                // input + skill cards via ChatPanelView). Brief placeholder while
                // we resolve which thread to open.
                VStack { Spacer(); ProgressView().tint(.secondary); Spacer() }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .background(Color.appBackground)
            }
        }
        .task { await initialEnter() }
    }

    /// First entry: load threads, then open the most recent so the tab opens
    /// like a regular thread. If the project has none yet, create one so the
    /// "Hi, <name>." greeting + composer show immediately.
    private func initialEnter() async {
        guard !didAutoOpen else { return }
        didAutoOpen = true
        await load()
        guard selectedThreadId == nil, !showList else { return }
        if let latest = threads.max(by: { $0.lastActivityAt < $1.lastActivityAt }) {
            openThread(id: latest.id)
        } else {
            await newThread()
        }
    }

    // MARK: List

    private var threadList: some View {
        VStack(spacing: 0) {
            HStack {
                Text("Threads")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundColor(appState.themeText)
                Spacer()
                Button {
                    Task { await newThread() }
                } label: {
                    HStack(spacing: 4) {
                        if creating {
                            ProgressView().controlSize(.small)
                        } else {
                            Image(systemName: "plus")
                        }
                        Text("New thread").font(.system(size: 11, weight: .medium))
                    }
                }
                .buttonStyle(.borderless)
                .disabled(creating)
                .help("Start a new AI thread in this project")
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)

            Divider().opacity(0.2)

            if isLoading && threads.isEmpty {
                Spacer()
                ProgressView()
                Spacer()
            } else if let err = errorMessage {
                Spacer()
                VStack(spacing: 8) {
                    Image(systemName: "exclamationmark.triangle").foregroundColor(.orange)
                    Text(err).font(.system(size: 11)).foregroundColor(.secondary)
                        .multilineTextAlignment(.center).padding(.horizontal, 24)
                    Button("Retry") { Task { await load() } }.buttonStyle(.bordered)
                }
                Spacer()
            } else if threads.isEmpty {
                Spacer()
                Text("No threads yet — start one to chat with AI about this workspace.")
                    .font(.system(size: 11)).foregroundColor(.secondary)
                    .multilineTextAlignment(.center).padding(.horizontal, 24)
                Spacer()
            } else {
                ScrollView {
                    LazyVStack(spacing: 4) {
                        ForEach(threads) { thread in
                            threadRow(thread)
                        }
                    }
                    .padding(10)
                }
            }
        }
    }

    private func threadRow(_ thread: MWThread) -> some View {
        let isOwner = thread.createdBy == nil || thread.createdBy == currentUserId
        let isShared = (thread.collaboratorCount ?? 0) > 0 || !isOwner
        let shareTargets = collaborators.filter { $0.userId != currentUserId }

        return HStack(spacing: 8) {
            Button { openThread(id: thread.id) } label: {
                VStack(alignment: .leading, spacing: 3) {
                    HStack(spacing: 6) {
                        Text(thread.title)
                            .font(.system(size: 12, weight: .medium))
                            .foregroundColor(appState.themeText)
                            .lineLimit(1)
                        if isShared {
                            Text("Shared")
                                .font(.system(size: 9, weight: .medium))
                                .padding(.horizontal, 5).padding(.vertical, 1)
                                .background(appState.themeAccent.opacity(0.2))
                                .foregroundColor(appState.themeAccent)
                                .cornerRadius(4)
                        }
                    }
                    if let when = PacificDateFormatter.relative(thread.lastActivityAt) {
                        Text(when).font(.system(size: 10)).foregroundColor(.secondary)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .buttonStyle(.plain)

            if isOwner && !shareTargets.isEmpty {
                Menu {
                    ForEach(shareTargets) { c in
                        Button("Share with \(c.name)") {
                            Task { await share(threadId: thread.id, userId: c.userId) }
                        }
                    }
                } label: {
                    Image(systemName: "person.badge.plus").font(.system(size: 11))
                }
                .menuStyle(.borderlessButton)
                .fixedSize()
                .help("Share this thread with a collaborator")
            }
        }
        .padding(10)
        .background(appState.themeCard.opacity(0.5))
        .cornerRadius(6)
    }

    // MARK: Detail

    private func threadDetail(id: String) -> some View {
        VStack(spacing: 0) {
            HStack(spacing: 8) {
                Button {
                    selectedThreadId = nil
                    showList = true
                    Task { await load() }
                } label: {
                    HStack(spacing: 4) {
                        Image(systemName: "chevron.left")
                        Text("Threads").font(.system(size: 11, weight: .medium))
                    }
                }
                .buttonStyle(.borderless)

                Text(threadVM.thread?.title ?? "Chat")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundColor(appState.themeText)
                    .lineLimit(1)
                Spacer()
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)

            Divider().opacity(0.2)

            ChatPanelView(viewModel: threadVM, lightMode: lightMode, selectedModel: selectedModel)
        }
    }

    // MARK: Actions

    private func load() async {
        isLoading = true
        errorMessage = nil
        do {
            threads = try await service.listProjectChats(projectId: projectId)
        } catch {
            errorMessage = error.localizedDescription
        }
        isLoading = false
    }

    private func openThread(id: String) {
        showList = false
        selectedThreadId = id
        Task { await threadVM.loadThread(id: id) }
    }

    private func newThread() async {
        creating = true
        defer { creating = false }
        do {
            let thread = try await service.createProjectChat(projectId: projectId)
            await load()
            openThread(id: thread.id)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func share(threadId: String, userId: String) async {
        do {
            try await service.addThreadCollaborator(threadId: threadId, userId: userId)
            await load()
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
