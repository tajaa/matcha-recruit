import Foundation
import AppKit

/// Reports desktop usage to the same `/usage/beacon` endpoint the web app uses,
/// so Werk sessions show up alongside web activity in /admin/usage.
///
/// Two events only: `session_start` when a signed-in session begins (launch with
/// a stored token, or login), and a `heartbeat` every 15 minutes while the app is
/// actually frontmost. The isActive gate matters — an app left open for a week in
/// the background would otherwise look like a week of continuous use.
///
/// Fire-and-forget: every failure is swallowed. Analytics must never interrupt
/// the app, and a dropped beacon costs nothing.
@MainActor
final class UsageBeaconService {
    static let shared = UsageBeaconService()

    private var heartbeatTimer: Timer?
    private let heartbeatInterval: TimeInterval = 15 * 60

    private init() {}

    private struct BeaconEvent: Encodable {
        let event: String
        let path: String
        let surface: String
    }

    private struct BeaconBody: Encodable {
        let events: [BeaconEvent]
    }

    /// Begin reporting for a signed-in session. Safe to call repeatedly.
    func start() {
        guard heartbeatTimer == nil else { return }

        send(event: "session_start")

        let timer = Timer.scheduledTimer(withTimeInterval: heartbeatInterval, repeats: true) { [weak self] _ in
            Task { @MainActor in
                guard NSApplication.shared.isActive else { return }
                self?.send(event: "heartbeat")
            }
        }
        // .common so the beat survives menu/tracking run-loop modes.
        RunLoop.main.add(timer, forMode: .common)
        heartbeatTimer = timer
    }

    /// Stop reporting (logout, or auth failure).
    func stop() {
        heartbeatTimer?.invalidate()
        heartbeatTimer = nil
    }

    private func send(event: String) {
        let body = BeaconBody(events: [
            BeaconEvent(event: event, path: "/werk", surface: "werk_desktop")
        ])
        Task {
            // The endpoint returns 204 with no body, so requestData (raw bytes,
            // no decode) rather than request<T: Decodable>.
            _ = try? await APIClient.shared.requestData(
                method: "POST",
                path: "/usage/beacon",
                body: body,
                retryOnUnauthorized: false
            )
        }
    }
}
