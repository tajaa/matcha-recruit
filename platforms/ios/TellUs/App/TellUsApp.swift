import SwiftUI

@main
struct TellUsApp: App {
    @State private var appState = AppState()
    @Environment(\.scenePhase) private var scenePhase

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(appState)
                .onChange(of: scenePhase) { _, phase in
                    if phase == .active {
                        appState.resumePolling()
                    } else {
                        appState.pausePolling()
                    }
                }
        }
    }
}
