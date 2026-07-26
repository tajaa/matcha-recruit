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

/// Broadcast mode — picked at start time. `.video` enables camera + mic at
/// connect; `.audio` skips the camera grab entirely so a call works in places
/// where video would be too heavy (or where users just want voice). Both
/// modes use the same LiveKit room; mode is purely a publisher-side track
/// choice and the server doesn't need to know.
enum BroadcastMode: String {
    case video, audio
}

/// User-selectable broadcast quality. Caps publisher encoder bitrate/fps and
/// picks subscriber simulcast layer for viewers. Default `.auto` lets the SDK
/// negotiate; explicit tiers help when the network is too slow for auto-detect
/// to recover (e.g. spotty WiFi where publisher upload chokes).
enum BroadcastQuality: String, CaseIterable, Identifiable {
    case auto, hd, sd, low
    var id: String { rawValue }
    var label: String {
        switch self {
        case .auto: return "Auto"
        case .hd: return "HD · 720p"
        case .sd: return "SD · 480p"
        case .low: return "Low · 360p"
        }
    }
    #if canImport(LiveKit)
    var dimensions: Dimensions {
        switch self {
        case .auto, .hd: return Dimensions(width: 1280, height: 720)
        case .sd:        return Dimensions(width: 854, height: 480)
        case .low:       return Dimensions(width: 640, height: 360)
        }
    }
    var fps: Int {
        switch self {
        case .auto, .hd: return 30
        case .sd:        return 24
        case .low:       return 15
        }
    }
    /// `nil` = SDK chooses (auto). Explicit caps for slow networks.
    var maxBitrate: Int? {
        switch self {
        case .auto: return nil
        case .hd:   return 1_700_000
        case .sd:   return 800_000
        case .low:  return 350_000
        }
    }
    /// Viewer-side simulcast layer pick.
    var subscriberQuality: VideoQuality {
        switch self {
        case .auto, .hd: return .high
        case .sd:        return .medium
        case .low:       return .low
        }
    }
    #endif
}

@Observable
@MainActor
final class BroadcastService {
    static let shared = BroadcastService()
    private init() {
        if let raw = UserDefaults.standard.string(forKey: BroadcastService.qualityPrefKey),
           let q = BroadcastQuality(rawValue: raw) {
            preferredQuality = q
        }
    }
    private static let qualityPrefKey = "broadcast.preferredQuality"

    // MARK: - Published state

    var isConnected = false
    var isPublishing = false   // true = this client has camera/mic on-stage
    var isOwner = false
    var channelId: String?
    var broadcastId: String?
    var liveKitUrl: String?
    var publisherUserIds: Set<String> = []
    /// Active broadcast mode — set at start. Drives whether camera is
    /// auto-enabled at connect and whether the panel renders the video grid
    /// or the audio-only banner. Viewers default to `.video` so the panel
    /// renders any video tracks remote publishers happen to push.
    var mode: BroadcastMode = .video
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
    /// User-selected broadcast quality. Loaded from UserDefaults in init().
    /// Mutated only via setQuality(_:) so we can apply the change to the live
    /// LiveKit room (republish camera with new options or set subscriber layer).
    var preferredQuality: BroadcastQuality = .auto
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

    func startBroadcast(channelId: String, title: String? = nil, mode: BroadcastMode = .video) async {
        errorMessage = nil
        isOwner = true
        self.channelId = channelId
        self.mode = mode

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

    func promote(userId: String, channelId: String) async throws {
        let _: OkResp = try await post(
            path: "/channels/\(channelId)/broadcast/promote",
            body: PromoteBody(user_id: userId)
        )
    }

    func demote(userId: String, channelId: String) async throws {
        let _: OkResp = try await post(
            path: "/channels/\(channelId)/broadcast/demote",
            body: PromoteBody(user_id: userId)
        )
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
                try await room.localParticipant.setCamera(
                    enabled: enabled,
                    captureOptions: enabled ? cameraCaptureOptions() : nil,
                    publishOptions: enabled ? videoPublishOptions() : nil
                )
                localCameraEnabled = enabled
                errorMessage = nil
                print("[Broadcast] setCameraEnabled(\(enabled)) ok quality=\(preferredQuality.rawValue)")
            } catch {
                print("[Broadcast] setCameraEnabled(\(enabled)) failed: \(error)")
                errorMessage = "Camera toggle failed: \(error.localizedDescription)"
            }
        }
        #endif
    }

    /// Update the preferred broadcast quality. Persists to UserDefaults and
    /// applies to the live room: publisher republishes camera at the new
    /// dimensions/bitrate, viewer requests the matching simulcast layer.
    func setQuality(_ quality: BroadcastQuality) {
        guard quality != preferredQuality else { return }
        preferredQuality = quality
        UserDefaults.standard.set(quality.rawValue, forKey: BroadcastService.qualityPrefKey)
        print("[Broadcast] setQuality \(quality.rawValue)")
        #if canImport(LiveKit)
        Task { @MainActor in await applyQualityChange() }
        #endif
    }

    #if canImport(LiveKit)
    private func cameraCaptureOptions() -> CameraCaptureOptions {
        CameraCaptureOptions(
            dimensions: preferredQuality.dimensions,
            fps: preferredQuality.fps
        )
    }

    private func videoPublishOptions() -> VideoPublishOptions? {
        guard let bitrate = preferredQuality.maxBitrate else { return nil }
        return VideoPublishOptions(
            encoding: VideoEncoding(maxBitrate: bitrate, maxFps: preferredQuality.fps),
            simulcast: true
        )
    }

    private func applyQualityChange() async {
        guard isConnected else { return }
        if isPublishing && localCameraEnabled {
            // Republish with new capture/publish options. setCamera(enabled:false)
            // first to drop the existing track, then re-enable with new options.
            do {
                try await room.localParticipant.setCamera(enabled: false)
                try await room.localParticipant.setCamera(
                    enabled: true,
                    captureOptions: cameraCaptureOptions(),
                    publishOptions: videoPublishOptions()
                )
                print("[Broadcast] applyQualityChange republished at \(preferredQuality.rawValue)")
            } catch {
                print("[Broadcast] applyQualityChange failed: \(error)")
                errorMessage = "Quality switch failed: \(error.localizedDescription)"
            }
        } else if !isPublishing {
            // Viewer: ask each remote video pub for the matching simulcast layer.
            let target = preferredQuality.subscriberQuality
            for participant in room.remoteParticipants.values {
                for (_, pub) in participant.trackPublications where pub.kind == .video {
                    if let remote = pub as? RemoteTrackPublication {
                        try? await remote.set(videoQuality: target)
                    }
                }
            }
            print("[Broadcast] applyQualityChange subscriber pref=\(target)")
        }
    }
    #endif

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
                // Hydrate publisher set from the REST snapshot. Otherwise
                // the InviteToBroadcastSheet shows promoted members as
                // "not on stage" until the next publisher_changed WS event,
                // which only fires on subsequent promote/demote calls.
                // Only mutate when we're actually in this channel's broadcast
                // — keeps unrelated channel polls from clobbering live state.
                if self.channelId == channelId, let ids = status.publisherUserIds {
                    publisherUserIds = Set(ids)
                }
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
            // Audio-only mode skips the camera permission prompt entirely so
            // a user who declined camera access can still join voice calls.
            if mode == .video {
                camOK = await AVCaptureDevice.requestAccess(for: .video)
            } else {
                camOK = false
            }
            micOK = await AVCaptureDevice.requestAccess(for: .audio)
            print("[Broadcast] permissions: cam=\(camOK) mic=\(micOK) mode=\(mode.rawValue)")
            if !micOK {
                errorMessage = "Microphone access denied. Open System Settings → Privacy & Security → Microphone and enable Matcha."
            }
        }

        do {
            try await room.connect(url: url, token: token)
            isConnected = true
            print("[Broadcast] room.connect OK identity=\(room.localParticipant.identity?.stringValue ?? "?")")

            if asPublisher {
                if mode == .video {
                    do {
                        try await room.localParticipant.setCamera(
                            enabled: camOK,
                            captureOptions: camOK ? cameraCaptureOptions() : nil,
                            publishOptions: camOK ? videoPublishOptions() : nil
                        )
                        localCameraEnabled = camOK
                        print("[Broadcast] camera enabled=\(camOK) quality=\(preferredQuality.rawValue)")
                    } catch {
                        print("[Broadcast] setCamera failed: \(error)")
                        errorMessage = "Camera failed: \(error.localizedDescription)"
                        localCameraEnabled = false
                    }
                } else {
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
        mode = .video
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
// Nonisolated: LiveKit calls RoomDelegate methods off the main actor, so the
// class can't be @MainActor (that conformance crosses actors / data-races).
// Every main-actor mutation hops via tickService()'s `Task { @MainActor }`.
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
