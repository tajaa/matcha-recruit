import Foundation
import Observation
import UIKit
import UserNotifications

@MainActor @Observable
final class PushService {
    static let shared = PushService()
    private init() {}

    private(set) var lastError: String?
    private(set) var isRegistered = false
    private var deviceToken: String? = KeychainHelper.load(key: KeychainHelper.Keys.pushToken)

    private struct RegisterBody: Encodable {
        let token: String
        let platform = "ios"
        let bundle_id: String
        let environment: String
    }
    private struct UnregisterBody: Encodable { let token: String }

    private var environment: String {
        #if DEBUG
        "sandbox"
        #else
        "production"
        #endif
    }

    func authorizationStatus() async -> UNAuthorizationStatus {
        await withCheckedContinuation { continuation in
            UNUserNotificationCenter.current().getNotificationSettings { settings in
                continuation.resume(returning: settings.authorizationStatus)
            }
        }
    }

    func activate() async {
        let status = await authorizationStatus()
        let authorized: Bool
        if status == .notDetermined {
            authorized = await withCheckedContinuation { continuation in
                UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .badge, .sound]) { granted, _ in
                    continuation.resume(returning: granted)
                }
            }
        } else {
            authorized = status == .authorized || status == .provisional || status == .ephemeral
        }
        if authorized {
            UIApplication.shared.registerForRemoteNotifications()
            await register()
        } else {
            isRegistered = false
            if let deviceToken { try? await unregister(token: deviceToken) }
        }
    }

    func updateDeviceToken(_ token: String) {
        let previous = deviceToken
        deviceToken = token
        _ = KeychainHelper.save(key: KeychainHelper.Keys.pushToken, value: token)
        Task {
            if let previous, previous != token { try? await unregister(token: previous) }
            await register()
        }
    }

    func register() async {
        guard let token = deviceToken, APIClient.shared.accessToken != nil else { return }
        let bundle = Bundle.main.bundleIdentifier ?? "com.heymatcha.schedule"
        do {
            _ = try await APIClient.shared.requestData(
                method: "POST", path: "/push/register",
                body: RegisterBody(token: token, bundle_id: bundle, environment: environment)
            )
            isRegistered = true
            lastError = nil
        } catch {
            isRegistered = false
            lastError = error.localizedDescription
        }
    }

    func unregister() async throws {
        guard let token = deviceToken else { return }
        try await unregister(token: token)
        isRegistered = false
    }

    private func unregister(token: String) async throws {
        guard APIClient.shared.accessToken != nil else { return }
        _ = try await APIClient.shared.requestData(
            method: "POST", path: "/push/unregister", body: UnregisterBody(token: token)
        )
    }
}
