import SwiftUI

/// iOS entry point for Espresso. Shares the networking/model/chat-logic core
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
                .tint(EspressoStyle.accent)
                .environment(appState)
                .environment(callService)
                .environment(broadcastService)
        }
        .onChange(of: scenePhase) { _, phase in
            switch phase {
            case .active:
                appState.isSceneActive = true
                // iOS suspends the socket in the background; re-open on return.
                if appState.isAuthenticated {
                    ChannelsWebSocket.shared.connect()
                    ProjectWebSocket.shared.connect()
                    Task { await appState.refreshSubscription() }
                }
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
            #if DEBUG
            if ProcessInfo.processInfo.arguments.contains("-espresso-preview") {
                MobileDesignPreview().allowsHitTesting(false)
            } else { sessionContent }
            #else
            sessionContent
            #endif
        }
    }

    private var sessionContent: some View {
        Group {
            if !appState.didRestore {
                ProgressView().controlSize(.large)
            } else if appState.isAuthenticated {
                MainTabView(initialTab: appState.pendingProjectId != nil ? 0 : appState.pendingConversationId != nil ? 2 : appState.pendingChannelId != nil ? 1 : 0)
            } else {
                LoginView()
            }
        }
    }
}
