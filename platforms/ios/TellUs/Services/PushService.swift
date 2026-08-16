import Foundation

/// Registers this device's APNs token with the Tell-Us backend so server-side
/// bell notifications (fan-board posts, campaign starts, reviews, messages,
/// and board comments) also push to the phone. Backend: `POST /push/register`
/// and `POST /push/unregister`.
@MainActor
final class PushService {
    static let shared = PushService()
    private init() {}

    private let bundleId = Bundle.main.bundleIdentifier ?? "com.beetlejuse.app"
    private(set) var deviceToken: String?

    private struct RegisterBody: Encodable {
        let token: String
        let platform: String
        let bundle_id: String
        let latitude: Double?
        let longitude: Double?
    }
    private struct LocationBody: Encodable {
        let token: String
        let latitude: Double
        let longitude: Double
    }
    private struct UnregisterBody: Encodable { let token: String }
    private struct OkResp: Decodable { let ok: Bool }

    /// Called from `AppDelegate.didRegisterForRemoteNotifications…` with the
    /// hex token. Caches it and registers (a no-op until logged in).
    func updateDeviceToken(_ token: String) {
        deviceToken = token
        Task { await register() }
    }

    func register() async {
        guard let token = deviceToken, APIClient.shared.accessToken != nil else { return }
        let coordinate = await LocationService.shared.requestAuthorizedOnce()
        do {
            let _: OkResp = try await APIClient.shared.request(
                method: "POST", path: "/push/register",
                body: RegisterBody(
                    token: token, platform: "ios", bundle_id: bundleId,
                    latitude: coordinate?.latitude, longitude: coordinate?.longitude
                )
            )
        } catch {
            print("[Push] register failed: \(error.localizedDescription)")
        }
    }

    func refreshLocation() async {
        guard let token = deviceToken, APIClient.shared.accessToken != nil,
              let coordinate = await LocationService.shared.requestAuthorizedOnce() else { return }
        do {
            let _: OkResp = try await APIClient.shared.request(
                method: "POST", path: "/push/location",
                body: LocationBody(token: token, latitude: coordinate.latitude, longitude: coordinate.longitude)
            )
        } catch {
            print("[Push] location update failed: \(error.localizedDescription)")
        }
    }

    func unregister() async {
        guard let token = deviceToken else { return }
        try? await APIClient.shared.requestVoid(
            method: "POST", path: "/push/unregister", body: UnregisterBody(token: token)
        )
    }
}
