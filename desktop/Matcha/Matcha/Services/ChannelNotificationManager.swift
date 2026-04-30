import Foundation
import UserNotifications

final class ChannelNotificationManager {
    static let shared = ChannelNotificationManager()
    static let enabledKey = "mw-channel-notifications-enabled"

    private init() {}

    func requestPermission() {
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound]) { _, _ in }
    }

    var isEnabled: Bool {
        // Default true — treat missing key as enabled
        UserDefaults.standard.object(forKey: Self.enabledKey) == nil
            ? true
            : UserDefaults.standard.bool(forKey: Self.enabledKey)
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
