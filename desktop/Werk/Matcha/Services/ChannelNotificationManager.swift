import AppKit
import Foundation
import UserNotifications

final class ChannelNotificationManager {
    static let shared = ChannelNotificationManager()
    static let enabledKey = "mw-channel-notifications-enabled"
    static let appNotificationsEnabledKey = "mw-app-notifications-enabled"
    static let promptSuppressedKey = "mw-notification-prompt-suppressed"
    /// Independent gate for the "ting" sound that plays on incoming channel
    /// messages while Werk is frontmost. Split out from `enabledKey` so users
    /// can keep visual toasts on while muting the sound. Default true.
    static let soundEnabledKey = "mw-channel-sound-enabled"

    private init() {}

    /// Set when the user clicks "Don't ask again" on the in-app permission
    /// alert. The alert re-fires on every cold launch + scene activation
    /// otherwise — this flag is the only way to mute it.
    var promptSuppressed: Bool {
        get { UserDefaults.standard.bool(forKey: Self.promptSuppressedKey) }
        set { UserDefaults.standard.set(newValue, forKey: Self.promptSuppressedKey) }
    }

    /// Master toggle for non-channel-chat notifications (task assignments,
    /// mentions, project events). Separate from `isEnabled` which gates the
    /// starred-channel chat toast path so we can independently mute either.
    var appNotificationsEnabled: Bool {
        UserDefaults.standard.object(forKey: Self.appNotificationsEnabledKey) == nil
            ? true
            : UserDefaults.standard.bool(forKey: Self.appNotificationsEnabledKey)
    }

    /// Post a generic system notification — used by the bell-push path for
    /// task assignments, mentions, and anything else routed through
    /// `mw_notifications`. Channel-chat toasts still go through `post(...)`.
    /// `userInfo` rides on the OS notification so a banner click can deep-link
    /// back into the app (AppDelegate didReceive → handleNotificationLink).
    /// Keys: "link" (String) and/or "metadata" ([String: String]).
    func postSystem(title: String, body: String?, userInfo: [AnyHashable: Any]? = nil) {
        guard appNotificationsEnabled else { return }
        UNUserNotificationCenter.current().getNotificationSettings { settings in
            guard settings.authorizationStatus == .authorized else { return }
            let note = UNMutableNotificationContent()
            note.title = title
            if let body, !body.isEmpty { note.body = body }
            note.sound = .default
            if let userInfo { note.userInfo = userInfo }
            let req = UNNotificationRequest(
                identifier: UUID().uuidString,
                content: note,
                trigger: nil
            )
            UNUserNotificationCenter.current().add(req)
        }
    }

    func requestPermission() {
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound]) { _, _ in }
    }

    /// Check the current notification authorization and call back on the main
    /// thread with the status. Used by AppState on each scene activation to
    /// decide whether to show the OS dialog (notDetermined) or our own
    /// in-app re-prompt (denied — macOS won't re-show the OS dialog after
    /// the user has denied once).
    func checkAuthorizationStatus(_ completion: @escaping (UNAuthorizationStatus) -> Void) {
        UNUserNotificationCenter.current().getNotificationSettings { settings in
            DispatchQueue.main.async {
                completion(settings.authorizationStatus)
            }
        }
    }

    /// Open the macOS Notifications pane in System Settings. Used by the
    /// re-prompt flow when the user has previously denied permission — the
    /// only way to re-enable notifications is through Settings.
    func openSystemNotificationSettings() {
        if let url = URL(string: "x-apple.systempreferences:com.apple.preference.notifications") {
            NSWorkspace.shared.open(url)
        }
    }

    var isEnabled: Bool {
        // Default true — treat missing key as enabled
        UserDefaults.standard.object(forKey: Self.enabledKey) == nil
            ? true
            : UserDefaults.standard.bool(forKey: Self.enabledKey)
    }

    /// Independent of `isEnabled` so toasts can remain on while sounds are
    /// muted. Default true (missing key = enabled).
    var soundEnabled: Bool {
        UserDefaults.standard.object(forKey: Self.soundEnabledKey) == nil
            ? true
            : UserDefaults.standard.bool(forKey: Self.soundEnabledKey)
    }

    func playInAppSound() {
        guard soundEnabled else { return }
        (NSSound(named: "Tink") ?? NSSound(named: "Pop"))?.play()
    }

    func post(senderName: String, content: String, channelName: String?, channelId: String? = nil) {
        guard isEnabled else { return }
        UNUserNotificationCenter.current().getNotificationSettings { settings in
            guard settings.authorizationStatus == .authorized else { return }
            let note = UNMutableNotificationContent()
            note.title = channelName.map { "#\($0)" } ?? "Channel message"
            note.body = "\(senderName): \(content)"
            note.sound = .default
            if let channelId {
                // Click-to-open: lands the user in this channel.
                note.userInfo = ["metadata": ["channel_id": channelId]]
            }
            let req = UNNotificationRequest(
                identifier: UUID().uuidString,
                content: note,
                trigger: nil
            )
            UNUserNotificationCenter.current().add(req)
        }
    }
}
