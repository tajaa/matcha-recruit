import SwiftUI

@main
struct MatchaScheduleApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
    @State private var appState = AppState()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(appState)
                .tint(Color(red: 0.36, green: 0.24, blue: 0.18))
                .task { await appState.restore() }
        }
    }
}
