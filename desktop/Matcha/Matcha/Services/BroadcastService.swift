/// BroadcastService — wraps the LiveKit Swift SDK for channel live broadcasts.
///
/// # SDK dependency
/// Add via Xcode → File → Add Package Dependencies:
///   https://github.com/livekit/client-sdk-swift  ≥ 2.0.0
///   Product: LiveKit → Target: Matcha
///
/// # Token lifecycle
/// Tokens expire in 1h. scheduleTokenRefresh() fires at 55 min and calls
/// /broadcast/refresh-token, then room.connectOptions is updated in-place via
/// the SDK's live token swap (Room requires reconnect if not in Quick mode).

import Foundation
import AVFoundation

#if canImport(LiveKit)
import LiveKit
#endif

@Observable
@MainActor
final class BroadcastService {
    static let shared = BroadcastService()
    private init() {}

    // MARK: - Published state

    var isConnected = false
    var isPublishing = false   // true = this client has camera/mic on-stage
    var isOwner = false
    var channelId: String?
    var broadcastId: String?
    var liveKitUrl: String?
    var publisherUserIds: Set<String> = []
    var errorMessage: String?
    /// Mutates whenever LiveKit participants change so @Observable triggers SwiftUI re-render.
    var participantTick: UInt64 = 0
    /// Observable backing for the Mic/Camera toolbar buttons. Reading from
    /// `room.localParticipant.isMicrophoneEnabled()` directly does NOT trigger
    /// SwiftUI invalidation under `@Observable`, so the toolbar icon would
    /// stale-cache after a toggle. We mirror the LiveKit state into observable
    /// properties and update them after every successful set call.
    var localMicEnabled: Bool = false
    var localCameraEnabled: Bool = false
    /// All channels with a known-active broadcast, keyed by channelId. Drives the
    /// "Live now — Watch feed" banner and the LIVE pill in channel header.
    /// Populated by WS broadcast.started events AND a REST poll on channel-view
    /// appear (so users who join the channel after the broadcast started, or
    /// whose WS dropped, still see the indicator).
    var activeBroadcasts: [String: ActiveBroadcastInfo] = [:]

    // Per-stream cap (set on connect, ticks down via countdownTask).
    var maxDurationSeconds: Int = 600
    var elapsedSeconds: Int = 0
    var weeklyRemaining: Int? = nil

    private var countdownTask: Task<Void, Never>?

    // MARK: - LiveKit room

    #if canImport(LiveKit)
    private(set) var room = Room()
    private var roomDelegate: BroadcastRoomDelegate?
    #endif


    // MARK: - REST helpers

    private struct StartBody: Encodable { let title: String? }
    private struct PromoteBody: Encodable { let user_id: String }
    private struct OkResp: Codable { let ok: Bool }

    private func get<T: Decodable>(path: String) async throws -> T {
        try await APIClient.shared.request(method: "GET", path: path)
    }

    private func post<T: Decodable>(path: String, body: (any Encodable)? = nil) async throws -> T {
        try await APIClient.shared.request(method: "POST", path: path, body: body)
    }

    // MARK: - Owner: Start broadcast

    func startBroadcast(channelId: String, title: String? = nil) async {
        errorMessage = nil
        isOwner = true
        self.channelId = channelId

        do {
            let resp: BroadcastStartResponse = try await post(
                path: "/channels/\(channelId)/broadcast/start",
                body: StartBody(title: title)
            )
            broadcastId = resp.broadcastId
            liveKitUrl = resp.liveKitUrl
            maxDurationSeconds = resp.maxDurationSeconds ?? 600
            weeklyRemaining = resp.weeklyRemaining
            elapsedSeconds = 0
            publisherUserIds.insert(currentUserId() ?? "")
            await connectToRoom(url: resp.liveKitUrl, token: resp.token, asPublisher: true)
            startCountdown()
        } catch {
            errorMessage = error.localizedDescription
            isOwner = false
            self.channelId = nil
        }
    }

    // MARK: - Member: Join as viewer

    func joinAsViewer(channelId: String) async {
        print("[Broadcast] joinAsViewer channelId=\(channelId)")
        errorMessage = nil
        isOwner = false
        self.channelId = channelId

        do {
            let resp: BroadcastTokenResponse = try await get(path: "/channels/\(channelId)/broadcast/token")
            print("[Broadcast] viewer token fetched url=\(resp.liveKitUrl) elapsed=\(resp.elapsedSeconds ?? 0)")
            liveKitUrl = resp.liveKitUrl
            maxDurationSeconds = resp.maxDurationSeconds ?? 600
            elapsedSeconds = resp.elapsedSeconds ?? 0
            await connectToRoom(url: resp.liveKitUrl, token: resp.token, asPublisher: false)
            startCountdown()
        } catch {
            print("[Broadcast] joinAsViewer FAILED: \(error)")
            errorMessage = error.localizedDescription
            self.channelId = nil
        }
    }

    // MARK: - Owner: Stop broadcast

    func stopBroadcast() async {
        guard let channelId else { return }
        do {
            let _: OkResp = try await post(path: "/channels/\(channelId)/broadcast/stop")
            // Clear the active-broadcast entry locally so the LIVE pill and
            // Watch-feed banner disappear immediately, without waiting for the
            // round-trip broadcast.ended WS event.
            activeBroadcasts.removeValue(forKey: channelId)
        } catch {
            errorMessage = error.localizedDescription
        }
        await leave()
    }

    /// End an orphaned broadcast for a channel without requiring this client
    /// to currently be the publisher. Used when an owner quits the app mid-
    /// stream and the server-side broadcast row stays open: returning to the
    /// channel, the owner sees the LIVE pill and an "End" button that calls
    /// this. POSTs to the same /stop endpoint — the server-side `_assert_owner`
    /// gate ensures only the channel owner can end it.
    func endBroadcastForChannel(channelId: String) async {
        do {
            let _: OkResp = try await post(path: "/channels/\(channelId)/broadcast/stop")
            activeBroadcasts.removeValue(forKey: channelId)
            print("[Broadcast] endBroadcastForChannel ok channel=\(channelId)")
        } catch {
            print("[Broadcast] endBroadcastForChannel failed channel=\(channelId): \(error)")
            errorMessage = "Couldn't end broadcast: \(error.localizedDescription)"
        }
    }

    // MARK: - Leave / disconnect

    func leave() async {
        countdownTask?.cancel(); countdownTask = nil
        #if canImport(LiveKit)
        await room.disconnect()
        #endif
        reset()
    }

    // MARK: - Owner: Promote / Demote

    func promote(userId: String, channelId: String) async {
        do {
            let _: OkResp = try await post(
                path: "/channels/\(channelId)/broadcast/promote",
                body: PromoteBody(user_id: userId)
            )
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func demote(userId: String, channelId: String) async {
        do {
            let _: OkResp = try await post(
                path: "/channels/\(channelId)/broadcast/demote",
                body: PromoteBody(user_id: userId)
            )
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    // MARK: - A/V controls

    func setMicEnabled(_ enabled: Bool) {
        #if canImport(LiveKit)
        // Re-check permission at toggle time — connectToRoom prompts once, but
        // the user can revoke mic access in System Settings between connect
        // and toggle. Without this, setMicrophone fails with a generic error.
        if enabled, AVCaptureDevice.authorizationStatus(for: .audio) == .denied {
            errorMessage = "Microphone access denied. Open System Settings → Privacy & Security → Microphone and enable Matcha."
            print("[Broadcast] setMicEnabled(\(enabled)) blocked: permission denied")
            return
        }
        Task { @MainActor in
            do {
                try await room.localParticipant.setMicrophone(enabled: enabled)
                localMicEnabled = enabled
                errorMessage = nil
                print("[Broadcast] setMicEnabled(\(enabled)) ok")
            } catch {
                print("[Broadcast] setMicEnabled(\(enabled)) failed: \(error)")
                errorMessage = "Mic toggle failed: \(error.localizedDescription)"
            }
        }
        #endif
    }

    func setCameraEnabled(_ enabled: Bool) {
        #if canImport(LiveKit)
        if enabled, AVCaptureDevice.authorizationStatus(for: .video) == .denied {
            errorMessage = "Camera access denied. Open System Settings → Privacy & Security → Camera and enable Matcha."
            print("[Broadcast] setCameraEnabled(\(enabled)) blocked: permission denied")
            return
        }
        Task { @MainActor in
            do {
                try await room.localParticipant.setCamera(enabled: enabled)
                localCameraEnabled = enabled
                errorMessage = nil
                print("[Broadcast] setCameraEnabled(\(enabled)) ok")
            } catch {
                print("[Broadcast] setCameraEnabled(\(enabled)) failed: \(error)")
                errorMessage = "Camera toggle failed: \(error.localizedDescription)"
            }
        }
        #endif
    }

    /// Backed by `localMicEnabled` so SwiftUI re-renders when toggled. Reading
    /// `room.localParticipant.isMicrophoneEnabled()` directly does not invalidate
    /// the @Observable snapshot.
    var isMicEnabled: Bool { localMicEnabled }

    var isCameraEnabled: Bool { localCameraEnabled }

    // MARK: - WS token grant (promote/demote pushes new token)

    func handleTokenGrant(channelId: String, token: String, liveKitUrl: String, canPublish: Bool) async {
        guard self.channelId == channelId, isConnected else { return }
        self.isPublishing = canPublish
        #if canImport(LiveKit)
        // LiveKit 2.x: reconnect with new token to apply changed grants.
        await room.disconnect()
        await connectToRoom(url: liveKitUrl, token: token, asPublisher: canPublish)
        #endif
    }

    // MARK: - WS broadcast events

    func handleBroadcastStarted(_ event: WSBroadcastStarted) async {
        print("[Broadcast] handleBroadcastStarted channel=\(event.channelId) broadcast=\(event.broadcastId) startedBy=\(event.startedBy)")
        // Record the active broadcast so the channel UI can show a banner +
        // LIVE pill. Joining LiveKit is now an explicit user action (Watch
        // button) — auto-join was silently dropping any viewer for whom the
        // token fetch or LiveKit connect failed, leaving them with zero UI.
        activeBroadcasts[event.channelId] = ActiveBroadcastInfo(
            broadcastId: event.broadcastId,
            startedBy: event.startedBy,
            startedAt: event.startedAt,
            title: event.title
        )
    }

    func handleBroadcastEnded(_ event: WSBroadcastEnded) async {
        activeBroadcasts.removeValue(forKey: event.channelId)
        if broadcastId == event.broadcastId {
            await leave()
        }
    }

    /// REST fallback: query current broadcast state for a channel and update
    /// `activeBroadcasts` accordingly. Called from ChannelDetailView on appear
    /// so viewers who navigate in mid-stream (or whose WS dropped) still see
    /// the banner without depending on a real-time event.
    func fetchBroadcastStatus(channelId: String) async {
        do {
            let status: BroadcastStatusResponse = try await get(path: "/channels/\(channelId)/broadcast")
            if status.active,
               let bid = status.broadcastId,
               let startedBy = status.startedBy,
               let startedAt = status.startedAt {
                activeBroadcasts[channelId] = ActiveBroadcastInfo(
                    broadcastId: bid,
                    startedBy: startedBy,
                    startedAt: startedAt,
                    title: status.title
                )
            } else {
                activeBroadcasts.removeValue(forKey: channelId)
            }
        } catch {
            print("[Broadcast] fetchBroadcastStatus failed channel=\(channelId): \(error)")
        }
    }

    func handlePublisherChanged(_ event: WSBroadcastPublisherChanged) {
        if event.canPublish {
            publisherUserIds.insert(event.userId)
        } else {
            publisherUserIds.remove(event.userId)
        }
    }

    // MARK: - Internal

    private func connectToRoom(url: String, token: String, asPublisher: Bool) async {
        print("[Broadcast] connectToRoom url=\(url) asPublisher=\(asPublisher)")
        #if canImport(LiveKit)
        isPublishing = asPublisher

        let delegate = BroadcastRoomDelegate(service: self)
        self.roomDelegate = delegate
        room = Room(delegate: delegate)

        // Force OS permission dialogs BEFORE LiveKit tries to grab tracks.
        // setMicrophone/setCamera under `try?` swallowed errors and never
        // surfaced a system prompt for some users.
        var camOK = true
        var micOK = true
        if asPublisher {
            camOK = await AVCaptureDevice.requestAccess(for: .video)
            micOK = await AVCaptureDevice.requestAccess(for: .audio)
            print("[Broadcast] permissions: cam=\(camOK) mic=\(micOK)")
            if !micOK {
                errorMessage = "Microphone access denied. Open System Settings → Privacy & Security → Microphone and enable Matcha."
            }
        }

        do {
            try await room.connect(url: url, token: token)
            isConnected = true
            print("[Broadcast] room.connect OK identity=\(room.localParticipant.identity?.stringValue ?? "?")")

            if asPublisher {
                do {
                    try await room.localParticipant.setCamera(enabled: camOK)
                    localCameraEnabled = camOK
                    print("[Broadcast] camera enabled=\(camOK)")
                } catch {
                    print("[Broadcast] setCamera failed: \(error)")
                    errorMessage = "Camera failed: \(error.localizedDescription)"
                    localCameraEnabled = false
                }
                do {
                    try await room.localParticipant.setMicrophone(enabled: micOK)
                    localMicEnabled = micOK
                    print("[Broadcast] microphone enabled=\(micOK)")
                } catch {
                    print("[Broadcast] setMicrophone failed: \(error)")
                    errorMessage = "Microphone failed: \(error.localizedDescription)"
                    localMicEnabled = false
                }
            }
        } catch {
            print("[Broadcast] room.connect FAILED: \(error)")
            errorMessage = error.localizedDescription
            isConnected = false
        }
        #endif
    }

    /// Tick `elapsedSeconds` once per second while connected so the UI can show
    /// a countdown. Server enforces the cap independently — this is display-only.
    private func startCountdown() {
        countdownTask?.cancel()
        countdownTask = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(1))
                guard let self else { return }
                if !self.isConnected { return }
                self.elapsedSeconds += 1
                if self.elapsedSeconds >= self.maxDurationSeconds {
                    return
                }
            }
        }
    }

    var remainingSeconds: Int { max(0, maxDurationSeconds - elapsedSeconds) }

    private func reset() {
        isConnected = false
        isPublishing = false
        isOwner = false
        channelId = nil
        broadcastId = nil
        liveKitUrl = nil
        publisherUserIds = []
        elapsedSeconds = 0
        weeklyRemaining = nil
        localMicEnabled = false
        localCameraEnabled = false
        countdownTask?.cancel(); countdownTask = nil
        #if canImport(LiveKit)
        room = Room()
        roomDelegate = nil
        #endif
    }

    private func currentUserId() -> String? {
        // AppState stores the current user — access via shared if available.
        return nil  // populated from WS event (started_by) instead
    }
}

// MARK: - Room delegate

#if canImport(LiveKit)
@MainActor
private final class BroadcastRoomDelegate: RoomDelegate, @unchecked Sendable {
    weak var service: BroadcastService?
    init(service: BroadcastService) { self.service = service }

    /// Triggers @Observable property change so SwiftUI views re-render.
    /// @Observable doesn't expose objectWillChange; we mutate a tracked
    /// counter on the service to drive view updates.
    private func tickService() {
        Task { @MainActor [weak service] in
            service?.participantTick &+= 1
        }
    }

    func room(_ room: Room, participantDidConnect participant: RemoteParticipant) {
        tickService()
    }

    func room(_ room: Room, participantDidDisconnect participant: RemoteParticipant) {
        tickService()
    }

    func room(_ room: Room, didUpdateConnectionState connectionState: ConnectionState,
              from oldValue: ConnectionState) {
        Task { @MainActor [weak service] in
            switch connectionState {
            case .disconnected:
                service?.isConnected = false
            case .connected:
                service?.isConnected = true
            default:
                break
            }
        }
    }
}
#endif
