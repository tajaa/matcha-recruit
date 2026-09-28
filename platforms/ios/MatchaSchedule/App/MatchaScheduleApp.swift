import SwiftUI

@main
struct MatchaScheduleApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
    @State private var appState = AppState()
    @Environment(\.scenePhase) private var scenePhase

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(appState)
                .tint(Color(red: 0.36, green: 0.24, blue: 0.18))
                .task { await appState.restore() }
        }
        .onChange(of: scenePhase) { _, phase in
            // Messages and notices that arrived while backgrounded.
            if phase == .active { Task { await appState.refreshBadgesIfReady() } }
        }
    }
}
