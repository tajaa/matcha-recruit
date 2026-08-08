import SwiftUI

@main
struct GummfitApp: App {
    @State private var appState = AppState()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(appState)
                .tint(GummfitTheme.accent)
        }
    }
}
