import SwiftUI

/// iOS entry point for Werk (chat). Shares the networking/model/chat-logic core
/// with the macOS target (`Matcha/`) via target membership; the views here are
/// touch-native (NavigationStack), not the macOS split-pane layouts.
@main
struct WerkApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
    @State private var appState = AppState()
    @State private var callService = CallService.shared
    @State private var broadcastService = BroadcastService.shared
    @Environment(\.scenePhase) private var scenePhase

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(appState)
                .environment(callService)
                .environment(broadcastService)
        }
        .onChange(of: scenePhase) { _, phase in
            switch phase {
            case .active:
                appState.isSceneActive = true
                // iOS suspends the socket in the background; re-open on return.
                if appState.isAuthenticated { ChannelsWebSocket.shared.connect() }
            case .background, .inactive:
                appState.isSceneActive = false
            @unknown default:
                break
            }
        }
    }
}

private struct RootView: View {
    @Environment(AppState.self) private var appState

    var body: some View {
        Group {
            if !appState.didRestore {
                ProgressView().controlSize(.large)
            } else if appState.isAuthenticated {
                MainTabView()
            } else {
                LoginView()
            }
        }
    }
}
