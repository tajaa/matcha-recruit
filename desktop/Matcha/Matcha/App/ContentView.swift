import SwiftUI

struct ContentView: View {
    @Environment(AppState.self) private var appState
    @State private var threadListVM = ThreadListViewModel()

    var body: some View {
        @Bindable var appState = appState

        NavigationSplitView {
            ThreadListView(viewModel: threadListVM)
                .navigationSplitViewColumnWidth(min: 240, ideal: 280, max: 360)
        } detail: {
            if let threadId = appState.selectedThreadId {
                ThreadDetailView(threadId: threadId)
            } else {
                ZStack {
                    Color.appBackground.ignoresSafeArea()
                    VStack(spacing: 12) {
                        Image(systemName: "bubble.left.and.bubble.right")
                            .font(.system(size: 48))
                            .foregroundColor(.secondary)
                        Text("Select a thread to get started")
                            .foregroundColor(.secondary)
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
