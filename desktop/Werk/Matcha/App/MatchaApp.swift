import SwiftUI

@main
struct MatchaApp: App {
    @State private var appState = AppState()
    @State private var broadcastService = BroadcastService.shared
    @Environment(\.scenePhase) private var scenePhase

    private var colorScheme: ColorScheme {
        appState.appTheme == "light" ? .light : .dark
    }

    var body: some Scene {
        WindowGroup {
            Group {
                if appState.isAuthenticated {
                    ContentView()
                        .environment(appState)
                        .environment(broadcastService)
                } else {
                    LoginView()
                        .environment(appState)
                }
            }
            .preferredColorScheme(colorScheme)
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

        // macOS Settings scene — opened via Cmd+, or
        // "Werk → Settings…" in the menu bar.
        Settings {
            SettingsView()
                .environment(appState)
                .preferredColorScheme(colorScheme)
        }
    }
}
