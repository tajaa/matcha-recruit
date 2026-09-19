import AuthenticationServices
import Foundation
import UIKit
import UserNotifications

@MainActor
final class CheckoutService: NSObject, ASWebAuthenticationPresentationContextProviding {
    static let shared = CheckoutService()
    private var webSession: ASWebAuthenticationSession?

    func quote(lines: [CartLine]) async throws -> Quote {
        try await StorefrontAPI.shared.request(
            Config.current.sitePath + "/quote",
            method: "POST",
            body: ["items": lines.map(\.requestObject)],
            authenticated: false
        )
    }

    func checkout(lines: [CartLine], shopper: Shopper?) async throws -> Checkout {
        let intervals = Set(lines.compactMap(\.interval))
        if !intervals.isEmpty {
            guard shopper != nil else { throw APIError(status: 401, message: "Sign in to start a subscription.") }
            guard intervals.count == 1, lines.allSatisfy({ $0.interval != nil }) else {
                throw APIError(status: 422, message: "Check out recurring and one-time items separately.")
            }
            return try await StorefrontAPI.shared.request(
                Config.current.shopperPath + "/me/subscriptions/checkout",
                method: "POST",
                body: [
                    "items": lines.map(\.requestObject),
                    "interval": intervals.first!,
                    "success_url": Config.current.returnURL,
                    "cancel_url": Config.current.returnURL,
                ]
            )
        }

        return try await StorefrontAPI.shared.request(
            Config.current.sitePath + "/orders",
            method: "POST",
            body: [
                "customer_email": shopper?.email ?? "",
                "customer_name": shopper?.name ?? NSNull(),
                "items": lines.map(\.requestObject),
                "success_url": Config.current.returnURL,
                "cancel_url": Config.current.returnURL,
            ],
            authenticated: shopper != nil
        )
    }

    func openHostedCheckout(_ value: Checkout) async throws -> URL? {
        guard let raw = value.checkoutUrl, let url = URL(string: raw) else { return nil }
        return try await withCheckedThrowingContinuation { continuation in
            let session = ASWebAuthenticationSession(url: url, callbackURLScheme: Config.current.scheme) {
                callback, error in
                if let authError = error as? ASWebAuthenticationSessionError,
                   authError.code == .canceledLogin {
                    continuation.resume(returning: nil)
                } else if let error {
                    continuation.resume(throwing: error)
                } else {
                    continuation.resume(returning: callback)
                }
                self.webSession = nil
            }
            session.presentationContextProvider = self
            session.prefersEphemeralWebBrowserSession = false
            webSession = session
            guard session.start() else {
                webSession = nil
                continuation.resume(throwing: APIError(status: 0, message: "Could not open secure checkout."))
                return
            }
        }
    }

    func waitForOrder(token: String) async throws -> Order {
        var last: Order?
        for _ in 0..<15 {
            let value: Order = try await StorefrontAPI.shared.request(
                "/public/orders/\(token)", authenticated: false
            )
            last = value
            if ["paid", "fulfilled", "declined", "cancelled", "refunded"].contains(value.status) {
                return value
            }
            try await Task.sleep(for: .seconds(2))
        }
        guard let last else { throw APIError(status: 0, message: "Order status is not available yet.") }
        return last
    }

    func presentationAnchor(for session: ASWebAuthenticationSession) -> ASPresentationAnchor {
        let scenes = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }
        return scenes.flatMap(\.windows).first(where: \.isKeyWindow) ?? ASPresentationAnchor()
    }
}

final class StorefrontAppDelegate: NSObject, UIApplicationDelegate, UNUserNotificationCenterDelegate {
    func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil
    ) -> Bool {
        UNUserNotificationCenter.current().delegate = self
        return true
    }

    func application(_ application: UIApplication, didRegisterForRemoteNotificationsWithDeviceToken token: Data) {
        let value = token.map { String(format: "%02x", $0) }.joined()
        UserDefaults.standard.set(value, forKey: NotificationService.tokenKey)
        NotificationCenter.default.post(name: .storeDeviceToken, object: value)
    }

    func application(_ application: UIApplication, didFailToRegisterForRemoteNotificationsWithError error: Error) {
        // The simulator and devices without an APNs profile may legitimately
        // fail registration; browsing and checkout remain fully usable.
    }

    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification,
        withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void
    ) {
        completionHandler([.banner, .sound, .badge])
    }

    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        didReceive response: UNNotificationResponse,
        withCompletionHandler completionHandler: @escaping () -> Void
    ) {
        if let token = DeepLinkHandler.token(from: response.notification.request.content.userInfo) {
            NotificationCenter.default.post(name: .storeOrderLink, object: token)
        }
        completionHandler()
    }
}

@MainActor
final class NotificationService {
    static let shared = NotificationService()
    static let tokenKey = "cappe.storefront.device-token"
    private var observers: [NSObjectProtocol] = []

    private init() {
        observers.append(NotificationCenter.default.addObserver(
            forName: .storeDeviceToken, object: nil, queue: .main
        ) { notification in
            guard let token = notification.object as? String else { return }
            Task { @MainActor in await NotificationService.shared.register(token: token) }
        })
        observers.append(NotificationCenter.default.addObserver(
            forName: .storeSessionStarted, object: nil, queue: .main
        ) { _ in
            Task { @MainActor in await NotificationService.shared.registerCurrentDevice() }
        })
    }

    func requestAuthorization() async {
        let center = UNUserNotificationCenter.current()
        let granted = (try? await center.requestAuthorization(options: [.alert, .badge, .sound])) ?? false
        if granted { UIApplication.shared.registerForRemoteNotifications() }
    }

    func registerCurrentDevice() async {
        guard let token = UserDefaults.standard.string(forKey: Self.tokenKey) else { return }
        await register(token: token)
    }

    private func register(token: String) async {
        guard StorefrontAPI.shared.tokens != nil,
              let bundle = Bundle.main.bundleIdentifier
        else { return }
        #if DEBUG
        let environment = "sandbox"
        #else
        let environment = "production"
        #endif
        let version = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String
        let _: Empty? = try? await StorefrontAPI.shared.request(
            Config.current.shopperPath + "/me/devices",
            method: "POST",
            body: [
                "token": token,
                "bundle_id": bundle,
                "environment": environment,
                "app_version": version ?? NSNull(),
            ]
        )
    }

    func unregisterCurrentDevice() async {
        guard StorefrontAPI.shared.tokens != nil,
              let token = UserDefaults.standard.string(forKey: Self.tokenKey)
        else { return }
        let _: Empty? = try? await StorefrontAPI.shared.request(
            Config.current.shopperPath + "/me/devices/\(token)", method: "DELETE"
        )
    }
}
