/// CallService — wraps the LiveKit Swift SDK for 4-person channel audio calls.
///
/// Parallel to BroadcastService but intentionally simpler: audio only (the
/// server token grant restricts publishing to the microphone source), every
/// participant publishes, no quality tiers, no promote/demote. The owner picks
/// the join policy at start time (invite-only vs all members); the server
/// enforces it at token mint and LiveKit enforces the 4-person cap.

import Foundation
import AVFoundation

#if canImport(LiveKit)
import LiveKit
#endif

@Observable
@MainActor
final class CallService {
    static let shared = CallService()
    private init() {}

    // MARK: - Published state

    var isConnected = false
    var isOwner = false
    /// Set by AppState at login (no AppState singleton to reach back into).
    var currentUserId: String?
    var channelId: String?
    var callId: String?
    var mode: CallMode?
    var errorMessage: String?
    /// Mutates whenever LiveKit participants/speakers change so @Observable
    /// triggers SwiftUI re-render (same pattern as BroadcastService).
    var participantTick: UInt64 = 0
    /// Mirror of the LiveKit mic state — reading room.localParticipant directly
    /// does not invalidate @Observable snapshots (see BroadcastService note).
    var localMicEnabled: Bool = false
    var elapsedSeconds: Int = 0
    var maxParticipants: Int = 4
    /// All channels with a known-active call, keyed by channelId. Drives the
    /// "Call · n/4" pill and join banner. Populated by WS call.* events AND a
    /// REST poll on channel-view appear.
    var activeCalls: [String: ActiveCallInfo] = [:]

    private var elapsedTask: Task<Void, Never>?

    #if canImport(LiveKit)
    private(set) var room = Room()
    private var roomDelegate: CallRoomDelegate?
    #endif

    // MARK: - REST helpers

    private struct StartBody: Encodable {
        let mode: String
        let invited_user_ids: [String]
    }
    private struct InviteBody: Encodable { let user_ids: [String] }
    private struct OkResp: Codable { let ok: Bool }

    private func get<T: Decodable>(path: String) async throws -> T {
        try await APIClient.shared.request(method: "GET", path: path)
    }

    private func post<T: Decodable>(path: String, body: (any Encodable)? = nil) async throws -> T {
        try await APIClient.shared.request(method: "POST", path: path, body: body)
    }

    // MARK: - Owner: start / stop

    func startCall(channelId: String, mode: CallMode, invitedUserIds: [String] = []) async {
        errorMessage = nil
        isOwner = true
        self.channelId = channelId
        self.mode = mode

        do {
            let resp: CallStartResponse = try await post(
                path: "/channels/\(channelId)/call/start",
                body: StartBody(mode: mode.rawValue, invited_user_ids: invitedUserIds)
            )
            callId = resp.callId
            maxParticipants = resp.maxParticipants ?? 4
            elapsedSeconds = 0
            await connectToRoom(url: resp.liveKitUrl, token: resp.token)
            startElapsedTimer()
        } catch {
            print("[Call] startCall failed: \(error)")
            errorMessage = error.localizedDescription
            isOwner = false
            self.channelId = nil
            self.mode = nil
        }
    }

    func stopCall() async {
        guard let channelId else { return }
        await endCallForChannel(channelId: channelId)
        await leave()
    }

    /// End the channel's active call without requiring this client to be
    /// connected (orphan path: owner quit mid-call, row still open). Server's
    /// _assert_owner gate ensures only the channel owner can end it.
    func endCallForChannel(channelId: String) async {
        do {
            let _: OkResp = try await post(path: "/channels/\(channelId)/call/stop")
            // Clear locally so the pill/banner disappear without waiting for
            // the round-trip call.ended WS event.
            activeCalls.removeValue(forKey: channelId)
        } catch {
            print("[Call] endCallForChannel failed channel=\(channelId): \(error)")
            errorMessage = "Couldn't end call: \(error.localizedDescription)"
        }
    }

    // MARK: - Member: join

    func joinCall(channelId: String) async {
        errorMessage = nil
        isOwner = activeCalls[channelId].map { $0.startedBy == currentUserId } ?? false
        self.channelId = channelId

        do {
            let resp: CallTokenResponse = try await get(path: "/channels/\(channelId)/call/token")
            mode = CallMode(rawValue: resp.mode)
            callId = activeCalls[channelId]?.callId
            maxParticipants = resp.maxParticipants ?? 4
            elapsedSeconds = resp.elapsedSeconds ?? 0
            await connectToRoom(url: resp.liveKitUrl, token: resp.token)
            startElapsedTimer()
        } catch {
            print("[Call] joinCall failed: \(error)")
            errorMessage = error.localizedDescription
            self.channelId = nil
        }
    }

    // MARK: - Owner: invite

    func invite(userIds: [String], channelId: String) async throws {
        let _: OkResp = try await post(
            path: "/channels/\(channelId)/call/invite",
            body: InviteBody(user_ids: userIds)
        )
        // Optimistic local update so the invite sheet reflects it immediately.
        if var info = activeCalls[channelId] {
            info.invitedUserIds.append(contentsOf: userIds.filter { !info.invitedUserIds.contains($0) })
            activeCalls[channelId] = info
        }
    }

    // MARK: - Leave / disconnect

    func leave() async {
        elapsedTask?.cancel(); elapsedTask = nil
        #if canImport(LiveKit)
        await room.disconnect()
        #endif
        reset()
    }

    // MARK: - Mic control

    func setMicEnabled(_ enabled: Bool) {
        #if canImport(LiveKit)
        if enabled, AVCaptureDevice.authorizationStatus(for: .audio) == .denied {
            errorMessage = "Microphone access denied. Open System Settings → Privacy & Security → Microphone and enable Matcha."
            return
        }
        Task { @MainActor in
            do {
                try await room.localParticipant.setMicrophone(enabled: enabled)
                localMicEnabled = enabled
                errorMessage = nil
            } catch {
                print("[Call] setMicEnabled(\(enabled)) failed: \(error)")
                errorMessage = "Mic toggle failed: \(error.localizedDescription)"
            }
        }
        #endif
    }

    var isMicEnabled: Bool { localMicEnabled }

    // MARK: - WS call events

    func handleCallStarted(_ event: WSCallStarted) {
        activeCalls[event.channelId] = ActiveCallInfo(
            callId: event.callId,
            startedBy: event.startedBy,
            startedAt: event.startedAt,
            mode: CallMode(rawValue: event.mode) ?? .members,
            participantIds: [event.startedBy],
            invitedUserIds: []
        )
    }

    func handleCallEnded(_ event: WSCallEnded) async {
        activeCalls.removeValue(forKey: event.channelId)
        if callId == event.callId {
            await leave()
        }
    }

    func handleCallInvited(_ event: WSCallInvited) {
        // Make sure the invitee's own client knows it may join (banner state).
        if var info = activeCalls[event.channelId] {
            if let me = currentUserId, !info.invitedUserIds.contains(me) {
                info.invitedUserIds.append(me)
                activeCalls[event.channelId] = info
            }
        }
    }

    func handleParticipantsChanged(_ event: WSCallParticipantsChanged) {
        if var info = activeCalls[event.channelId] {
            info.participantIds = event.participantIds
            activeCalls[event.channelId] = info
        }
    }

    /// REST fallback: hydrate call state for a channel on view appear, so
    /// members who navigate in mid-call (or whose WS dropped) see the banner.
    func fetchCallStatus(channelId: String) async {
        do {
            let status: CallStatusResponse = try await get(path: "/channels/\(channelId)/call")
            if status.active,
               let cid = status.callId,
               let startedBy = status.startedBy,
               let startedAt = status.startedAt {
                activeCalls[channelId] = ActiveCallInfo(
                    callId: cid,
                    startedBy: startedBy,
                    startedAt: startedAt,
                    mode: CallMode(rawValue: status.mode ?? "members") ?? .members,
                    participantIds: status.participantIds ?? [startedBy],
                    invitedUserIds: status.invitedUserIds ?? []
                )
            } else {
                activeCalls.removeValue(forKey: channelId)
            }
        } catch {
            print("[Call] fetchCallStatus failed channel=\(channelId): \(error)")
        }
    }

    // MARK: - Internal

    private func connectToRoom(url: String, token: String) async {
        #if canImport(LiveKit)
        let delegate = CallRoomDelegate(service: self)
        self.roomDelegate = delegate
        room = Room(delegate: delegate)

        // Prompt for mic BEFORE LiveKit grabs the track (same rationale as
        // BroadcastService: try? inside the SDK swallows the system prompt).
        let micOK = await AVCaptureDevice.requestAccess(for: .audio)
        if !micOK {
            errorMessage = "Microphone access denied. Open System Settings → Privacy & Security → Microphone and enable Matcha."
        }

        do {
            try await room.connect(url: url, token: token)
            isConnected = true
            do {
                try await room.localParticipant.setMicrophone(enabled: micOK)
                localMicEnabled = micOK
            } catch {
                print("[Call] setMicrophone failed: \(error)")
                errorMessage = "Microphone failed: \(error.localizedDescription)"
                localMicEnabled = false
            }
        } catch {
            print("[Call] room.connect FAILED: \(error)")
            errorMessage = error.localizedDescription
            isConnected = false
        }
        #endif
    }

    private func startElapsedTimer() {
        elapsedTask?.cancel()
        elapsedTask = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(1))
                guard let self else { return }
                if !self.isConnected { return }
                self.elapsedSeconds += 1
            }
        }
    }

    private func reset() {
        isConnected = false
        isOwner = false
        channelId = nil
        callId = nil
        mode = nil
        elapsedSeconds = 0
        localMicEnabled = false
        elapsedTask?.cancel(); elapsedTask = nil
        #if canImport(LiveKit)
        room = Room()
        roomDelegate = nil
        #endif
    }
}

// MARK: - Room delegate

#if canImport(LiveKit)
// Nonisolated: LiveKit calls RoomDelegate methods off the main actor (see
// BroadcastRoomDelegate). Main-actor mutations hop via Task { @MainActor }.
private final class CallRoomDelegate: RoomDelegate, @unchecked Sendable {
    weak var service: CallService?
    init(service: CallService) { self.service = service }

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

    /// Speaking indicators: LiveKit updates isSpeaking on participants and
    /// notifies here — tick so the rows re-read participant.isSpeaking.
    func room(_ room: Room, didUpdateSpeakingParticipants participants: [Participant]) {
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
