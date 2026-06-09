import SwiftUI
import AppKit
import UserNotifications

/// Owns the UNUserNotificationCenter delegate. Without a delegate, macOS
/// suppresses notification banners while the app is the active/foreground
/// process — so a message arriving while Werk is open behind another window
/// (or on another channel) showed no banner. `willPresent` opts every
/// notification into a banner + sound regardless of foreground state; the
/// decision of *whether* to post is made upstream in AppState.
final class AppDelegate: NSObject, NSApplicationDelegate, UNUserNotificationCenterDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        UNUserNotificationCenter.current().delegate = self
    }

    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification,
        withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void
    ) {
        completionHandler([.banner, .list, .sound])
    }
}

@main
struct MatchaApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
    @State private var appState = AppState()
    @State private var broadcastService = BroadcastService.shared
    @Environment(\.scenePhase) private var scenePhase

    private var colorScheme: ColorScheme {
        appState.isLightFamily ? .light : .dark
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
            // Cmd+F — the find-anything palette (surfaces + project files,
            // open into main/right/bottom pane, star to sidebar). ContentView
            // presents the sheet off this flag.
            CommandGroup(after: .textEditing) {
                Button("Find in Werk…") {
                    appState.showFinderPalette = true
                }
                .keyboardShortcut("f", modifiers: .command)
                .disabled(!appState.isAuthenticated)
            }
        }

        // Secondary windows — opened via openWindow(id:"aux", value:) from
        // sidebar context menus. Value-driven (one window per distinct target),
        // so the generic File > New Window stays suppressed above.
        WindowGroup(id: "aux", for: AuxWindowTarget.self) { $target in
            AuxWindowRootView(target: target)
                .environment(appState)
                .environment(broadcastService)
                .preferredColorScheme(colorScheme)
        }
        .windowStyle(.hiddenTitleBar)
        .defaultSize(width: 900, height: 700)

        // macOS Settings scene — opened via Cmd+, or
        // "Werk → Settings…" in the menu bar.
        Settings {
            SettingsView()
                .environment(appState)
                .preferredColorScheme(colorScheme)
        }
    }
}
