import SwiftUI

struct ContentView: View {
    @Environment(AppState.self) private var appState
    @State private var threadListVM = ThreadListViewModel()
    @State private var isCreating = false

    var body: some View {
        @Bindable var appState = appState

        NavigationSplitView {
            ThreadListView(viewModel: threadListVM)
                .navigationSplitViewColumnWidth(min: 240, ideal: 280, max: 360)
        } detail: {
            if let threadId = appState.selectedThreadId {
                ThreadDetailView(threadId: threadId)
                    .onChange(of: threadId) { appState.showSkills = false }
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
        .toolbar {
            ToolbarItem(placement: .status) {
                if let user = appState.currentUser {
                    HStack(spacing: 8) {
                        Text(user.email)
                            .font(.system(size: 12))
                            .foregroundColor(.secondary)
                        Button("Logout") {
                            Task {
                                try? await AuthService.shared.logout()
                                await MainActor.run { appState.didLogout() }
                            }
                        }
                        .buttonStyle(.plain)
                        .font(.system(size: 12))
                        .foregroundColor(.secondary)
                    }
                }
            }
        }
    }
}
