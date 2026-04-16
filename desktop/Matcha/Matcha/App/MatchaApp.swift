import SwiftUI

@main
struct MatchaApp: App {
    @State private var appState = AppState()
    @Environment(\.scenePhase) private var scenePhase

    var body: some Scene {
        WindowGroup {
            Group {
                if appState.isAuthenticated {
                    ContentView()
                        .environment(appState)
                } else {
                    LoginView()
                        .environment(appState)
                }
            }
            .preferredColorScheme(.dark)
            .onChange(of: scenePhase) { _, phase in
                appState.isSceneActive = (phase == .active)
                if phase == .active {
                    // When the app scene becomes active, retry session restore
                    // (fixes the case where the dev server wasn't running at
                    // launch) and nudge the channels WebSocket back to life.
                    Task { await appState.onSceneActive() }
                }
            }
        }
        .windowStyle(.hiddenTitleBar)
        .defaultSize(width: 1200, height: 800)
        .commands {
            CommandGroup(replacing: .newItem) { }
        }
    }
}
