import SwiftUI

@main
struct MatchaApp: App {
    @State private var appState = AppState()
    @Environment(\.scenePhase) private var scenePhase

    var body: some Scene {
        WindowGroup {
            if appState.isAuthenticated {
                ContentView()
                    .environment(appState)
                    .preferredColorScheme(.dark)
                    .onChange(of: scenePhase) { _, phase in
                        // When the user returns to the app (e.g. after
                        // completing Stripe checkout in the browser), re-pull
                        // the subscription so the Plus badge updates.
                        if phase == .active && appState.isAuthenticated {
                            Task { await appState.refreshSubscription() }
                        }
                    }
            } else {
                LoginView()
                    .environment(appState)
                    .preferredColorScheme(.dark)
            }
        }
        .windowStyle(.hiddenTitleBar)
        .defaultSize(width: 1200, height: 800)
        .commands {
            CommandGroup(replacing: .newItem) { }
        }
    }
}
