import SwiftUI

@main
struct MatchaScheduleApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
    @State private var appState = AppState()
    @Environment(\.scenePhase) private var scenePhase
    @AppStorage(AppearancePreference.storageKey) private var appearance = AppearancePreference.system

    init() {
        Appearance.configure()
    }

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(appState)
                .tint(Palette.leaf)
                .task { await appState.restore() }
                .onAppear { AppearancePreference.apply(appearance) }
                .onChange(of: appearance) { _, preference in
                    AppearancePreference.apply(preference, animated: true)
                }
        }
        .onChange(of: scenePhase) { _, phase in
            guard phase == .active else { return }
            // A window created while backgrounded (or a new scene) picks up
            // the saved appearance too.
            AppearancePreference.apply(appearance)
            // Messages and notices that arrived while backgrounded.
            Task { await appState.refreshBadgesIfReady() }
        }
    }
}
