import AppKit
import Foundation
import UserNotifications

final class ChannelNotificationManager {
    static let shared = ChannelNotificationManager()
    static let enabledKey = "mw-channel-notifications-enabled"

    private init() {}

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

    func playInAppSound() {
        guard isEnabled else { return }
        (NSSound(named: "Tink") ?? NSSound(named: "Pop"))?.play()
    }

    func post(senderName: String, content: String, channelName: String?) {
        guard isEnabled else { return }
        UNUserNotificationCenter.current().getNotificationSettings { settings in
            guard settings.authorizationStatus == .authorized else { return }
            let note = UNMutableNotificationContent()
            note.title = channelName.map { "#\($0)" } ?? "Channel message"
            note.body = "\(senderName): \(content)"
            note.sound = .default
            let req = UNNotificationRequest(
                identifier: UUID().uuidString,
                content: note,
                trigger: nil
            )
            UNUserNotificationCenter.current().add(req)
        }
    }
}
