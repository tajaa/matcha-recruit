import UIKit
import UserNotifications

/// iOS app delegate: owns APNs registration + the notification-center delegate
/// (foreground presentation + banner-tap deep-link relay).
final class AppDelegate: NSObject, UIApplicationDelegate, UNUserNotificationCenterDelegate {
    func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil
    ) -> Bool {
        UNUserNotificationCenter.current().delegate = self
        return true
    }

    // MARK: - APNs token

    func application(
        _ application: UIApplication,
        didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data
    ) {
        let hex = deviceToken.map { String(format: "%02x", $0) }.joined()
        Task { @MainActor in PushService.shared.updateDeviceToken(hex) }
    }

    func application(
        _ application: UIApplication,
        didFailToRegisterForRemoteNotificationsWithError error: Error
    ) {
        print("[Push] APNs registration failed: \(error.localizedDescription)")
    }

    // MARK: - UNUserNotificationCenterDelegate

    /// Show a banner even when the app is foregrounded (the server decides
    /// whether to send; the OS handles the rest).
    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification,
        withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void
    ) {
        completionHandler([.banner, .list, .sound])
    }

    /// Tap → relay the payload so `AppState` can deep-link to the channel/DM.
    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        didReceive response: UNNotificationResponse,
        withCompletionHandler completionHandler: @escaping () -> Void
    ) {
        let userInfo = response.notification.request.content.userInfo
        NotificationCenter.default.post(name: .werkDeepLink, object: nil, userInfo: userInfo)
        completionHandler()
    }
}

extension Notification.Name {
    /// Posted when the user taps a push; userInfo carries the APNs payload
    /// (`type`, `link`, `metadata` with channel_id / conversation_id).
    static let werkDeepLink = Notification.Name("werk-deep-link")
}
