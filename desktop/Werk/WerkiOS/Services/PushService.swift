import Foundation

/// Registers this device's APNs token with the backend so server-side bell
/// notifications (channel messages, DMs, mentions, calls) also push to the
/// phone. Backend: `POST /push/register` · `POST /push/unregister`.
@MainActor
final class PushService {
    static let shared = PushService()
    private init() {}

    private let bundleId = Bundle.main.bundleIdentifier ?? "com.matchawork.app"
    private(set) var deviceToken: String?

    private struct RegisterBody: Encodable {
        let token: String
        let platform: String
        let bundle_id: String
    }
    private struct UnregisterBody: Encodable { let token: String }
    private struct OkResp: Decodable { let ok: Bool }

    /// Called from `AppDelegate.didRegisterForRemoteNotifications…` with the hex
    /// token. Caches it and registers (a no-op until logged in).
    func updateDeviceToken(_ token: String) {
        deviceToken = token
        Task { await register() }
    }

    func register() async {
        guard let token = deviceToken, APIClient.shared.accessToken != nil else { return }
        do {
            let _: OkResp = try await APIClient.shared.request(
                method: "POST", path: "/push/register",
                body: RegisterBody(token: token, platform: "ios", bundle_id: bundleId)
            )
        } catch {
            print("[Push] register failed: \(error.localizedDescription)")
        }
    }

    func unregister() async {
        guard let token = deviceToken else { return }
        _ = try? await APIClient.shared.requestData(
            method: "POST", path: "/push/unregister", body: UnregisterBody(token: token)
        )
    }
}
