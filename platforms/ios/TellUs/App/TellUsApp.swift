import SwiftUI

@main
struct TellUsApp: App {
    @State private var appState = AppState()
    @Environment(\.scenePhase) private var scenePhase

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(appState)
                // Design is dark-only — the hand-built glass (ultraThinMaterial
                // over EmberBackground) needs a lit dark ground; a light scheme
                // has nothing luminous behind it.
                .preferredColorScheme(.dark)
                .tint(TU.ember)
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
