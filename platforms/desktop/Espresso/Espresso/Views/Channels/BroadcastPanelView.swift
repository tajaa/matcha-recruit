/// BroadcastPanelView — live video panel shown above chat when a broadcast is active.
///
/// Renders a tile grid of VideoViews (requires LiveKit Swift SDK ≥ 2.0.0).
/// Falls back to a static "Live" banner when the SDK is not linked.

import SwiftUI

#if canImport(LiveKit)
import LiveKit
#endif

struct BroadcastPanelView: View {
    let channelId: String
    let channelName: String
    let isOwner: Bool
    /// Channel members for the "Invite to stage" picker. Pulled from the
    /// parent ChannelDetailView's `channel.members` so the sheet doesn't
    /// have to re-fetch.
    let members: [ChannelMember]
    let myUserId: String

    @Environment(BroadcastService.self) private var broadcast: BroadcastService
    @State private var showInviteToStage = false
    /// Collapsed state shows only the header strip (LIVE pill + viewer
    /// count + expand button) so chat fills most of the channel pane.
    /// Persists per-channel so a user who collapses returns to a thin
    /// strip on rejoin. Persisted-key uses the channel id so different
    /// channels remember independently.
    @AppStorage private var collapsed: Bool

    init(channelId: String, channelName: String, isOwner: Bool, members: [ChannelMember], myUserId: String) {
        self.channelId = channelId
        self.channelName = channelName
        self.isOwner = isOwner
        self.members = members
        self.myUserId = myUserId
        self._collapsed = AppStorage(wrappedValue: false, "mw-broadcast-collapsed:\(channelId)")
    }

    var body: some View {
        VStack(spacing: 0) {
            header
            if !collapsed {
                videoGrid
                if let err = broadcast.errorMessage {
                    Text(err)
                        .font(.system(size: 10))
                        .foregroundColor(.red.opacity(0.85))
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.horizontal, 12)
                        .padding(.bottom, 4)
                }
                toolbar
            }
        }
        .background(Color.black.opacity(0.85))
        .cornerRadius(8)
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(Color.matcha600.opacity(0.4), lineWidth: 1)
        )
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
        .sheet(isPresented: $showInviteToStage) {
            InviteToBroadcastSheet(
                channelId: channelId,
                channelName: channelName,
                members: members,
                myUserId: myUserId,
            )
            .environment(broadcast)
        }
    }

    // MARK: - Header

    private var headerSubtitle: String {
        let live = broadcast.mode == .audio ? "audio call" : "live"
        return broadcast.isPublishing ? "You're on \(live)" : "Listening to \(live)"
    }

    private var header: some View {
        HStack(spacing: 8) {
            // LIVE pill
            Text("LIVE")
                .font(.system(size: 9, weight: .bold))
                .foregroundColor(.white)
                .padding(.horizontal, 6)
                .padding(.vertical, 2)
                .background(Color.red)
                .cornerRadius(3)

            Text(headerSubtitle)
                .font(.system(size: 11))
                .foregroundColor(.white.opacity(0.75))

            // Countdown
            let r = broadcast.remainingSeconds
            let mins = r / 60
            let secs = r % 60
            Text(String(format: "%d:%02d left", mins, secs))
                .font(.system(size: 10, weight: .medium, design: .monospaced))
                .foregroundColor(r < 60 ? .red : .white.opacity(0.6))

            Spacer()

            #if canImport(LiveKit)
            let viewerCount = broadcast.room.remoteParticipants.count + 1
            #else
            let viewerCount = 1
            #endif
            HStack(spacing: 3) {
                Image(systemName: "eye").font(.system(size: 9))
                Text("\(viewerCount)").font(.system(size: 10))
            }
            .foregroundColor(.white.opacity(0.5))

            // Collapse toggle — shrinks the panel to a thin LIVE strip so
            // chat fills the channel pane. State persists per-channel.
            Button {
                collapsed.toggle()
            } label: {
                Image(systemName: collapsed ? "chevron.down" : "chevron.up")
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundColor(.white.opacity(0.7))
                    .frame(width: 18, height: 18)
            }
            .buttonStyle(.plain)
            .help(collapsed ? "Expand video" : "Minimize to focus on chat")
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
    }

    // MARK: - Video grid

    @ViewBuilder
    private var videoGrid: some View {
        #if canImport(LiveKit)
        let _ = broadcast.participantTick  // observe ticks for re-render
        let publishers: [RemoteParticipant] = Array(broadcast.room.remoteParticipants.values)
            .filter { $0.firstCameraVideoTrack != nil }
        let hasLocalVideo = broadcast.room.localParticipant.isCameraEnabled()

        if publishers.isEmpty && !hasLocalVideo {
            audioOnlyBanner
        } else {
            let tileCount = publishers.count + (hasLocalVideo ? 1 : 0)
            let columns = max(1, min(3, tileCount))
            LazyVGrid(
                columns: Array(repeating: GridItem(.flexible(), spacing: 4), count: columns),
                spacing: 4
            ) {
                if hasLocalVideo {
                    localVideoTile
                }
                ForEach(publishers) { participant in
                    RemoteVideoTile(participant: participant)
                }
            }
            .padding(.horizontal, 8)
            .padding(.bottom, 4)
        }
        #else
        audioOnlyBanner
        #endif
    }

    private var audioOnlyBanner: some View {
        // Same banner whether mode is .audio (intentional) or .video with
        // no cameras yet on stage — both render visually identically.
        // Subtitle differs so the publisher knows their call type.
        HStack {
            Spacer()
            VStack(spacing: 6) {
                Image(systemName: "waveform.circle")
                    .font(.system(size: 28))
                    .foregroundColor(Color.matcha500)
                Text(broadcast.mode == .audio ? "Audio call" : "Audio broadcast")
                    .font(.system(size: 11))
                    .foregroundColor(.white.opacity(0.5))
            }
            Spacer()
        }
        .frame(height: 80)
    }

    @ViewBuilder
    private var localVideoTile: some View {
        #if canImport(LiveKit)
        // firstCameraVideoTrack gates on isSubscribed which is false for local
        // publications, so we go through firstCameraPublication directly.
        if let pub = broadcast.room.localParticipant.firstCameraPublication,
           !pub.isMuted,
           let track = pub.track as? VideoTrack {
            ZStack(alignment: .bottomLeading) {
                SwiftUIVideoView(track,
                                layoutMode: .fill,
                                mirrorMode: .mirror)
                    .aspectRatio(16.0/9.0, contentMode: .fit)
                    .frame(maxWidth: .infinity, minHeight: 160, maxHeight: 240)
                    .cornerRadius(6)
                    .clipped()
                Text("You")
                    .font(.system(size: 9, weight: .medium))
                    .foregroundColor(.white)
                    .padding(.horizontal, 5)
                    .padding(.vertical, 2)
                    .background(Color.black.opacity(0.55))
                    .cornerRadius(3)
                    .padding(4)
            }
        }
        #endif
    }

    // MARK: - Toolbar

    private var toolbar: some View {
        HStack(spacing: 12) {
            if broadcast.isPublishing {
                toolbarToggle(
                    on: broadcast.isMicEnabled,
                    icon: broadcast.isMicEnabled ? "mic.fill" : "mic.slash.fill",
                    label: "Mic"
                ) { broadcast.setMicEnabled(!broadcast.isMicEnabled) }

                // Camera toggle stays available in both modes — audio-only
                // can be upgraded to video on the fly with this button (and
                // setCameraEnabled re-prompts for camera permission as needed).
                toolbarToggle(
                    on: broadcast.isCameraEnabled,
                    icon: broadcast.isCameraEnabled ? "video.fill" : "video.slash.fill",
                    label: "Camera"
                ) { broadcast.setCameraEnabled(!broadcast.isCameraEnabled) }
            }

            // Quality only matters when video is in play. Hide for audio-only
            // calls so the toolbar isn't cluttered with irrelevant controls.
            if broadcast.mode == .video {
                qualityMenu
            }

            // Owner-only — promote channel members to publishers so you can
            // run a small group call (3+ people on stage). Backend gates
            // owner-only at /broadcast/promote; we mirror that on the trigger.
            if isOwner {
                Button {
                    showInviteToStage = true
                } label: {
                    HStack(spacing: 4) {
                        Image(systemName: "person.badge.plus").font(.system(size: 11))
                        Text("Invite").font(.system(size: 11, weight: .medium))
                    }
                    .padding(.horizontal, 8)
                    .padding(.vertical, 5)
                    .background(Color.matcha600.opacity(0.25))
                    .foregroundColor(Color.matcha500)
                    .cornerRadius(5)
                }
                .buttonStyle(.plain)
                .help("Invite channel members to the stage")
            }

            Spacer()

            if isOwner {
                Button(role: .destructive) {
                    Task { await broadcast.stopBroadcast() }
                } label: {
                    HStack(spacing: 4) {
                        Image(systemName: "stop.circle").font(.system(size: 10))
                        Text("End broadcast").font(.system(size: 11, weight: .medium))
                    }
                    .padding(.horizontal, 10)
                    .padding(.vertical, 5)
                    .background(Color.red.opacity(0.85))
                    .foregroundColor(.white)
                    .cornerRadius(5)
                }
                .buttonStyle(.plain)
            } else {
                Button {
                    Task { await broadcast.leave() }
                } label: {
                    HStack(spacing: 4) {
                        Image(systemName: "arrow.right.square").font(.system(size: 10))
                        Text("Leave").font(.system(size: 11, weight: .medium))
                    }
                    .padding(.horizontal, 10)
                    .padding(.vertical, 5)
                    .background(Color.zinc800)
                    .foregroundColor(.white.opacity(0.8))
                    .cornerRadius(5)
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(Color.black.opacity(0.4))
    }

    /// Resolution selector. Shown to publishers AND viewers — for publishers
    /// it caps the encoder upload bitrate/fps; for viewers it picks the matching
    /// simulcast layer. Useful when WiFi can't keep up with Auto.
    private var qualityMenu: some View {
        Menu {
            ForEach(BroadcastQuality.allCases) { q in
                Button {
                    broadcast.setQuality(q)
                } label: {
                    if broadcast.preferredQuality == q {
                        Label(q.label, systemImage: "checkmark")
                    } else {
                        Text(q.label)
                    }
                }
            }
        } label: {
            HStack(spacing: 3) {
                Image(systemName: "slider.horizontal.3").font(.system(size: 10))
                Text(broadcast.preferredQuality.label)
                    .font(.system(size: 10, weight: .medium))
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 6)
            .background(Color.zinc800.opacity(0.6))
            .foregroundColor(.white.opacity(0.85))
            .cornerRadius(5)
        }
        .menuStyle(.borderlessButton)
        .fixedSize()
    }

    private func toolbarToggle(on: Bool, icon: String, label: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            VStack(spacing: 2) {
                Image(systemName: icon)
                    .font(.system(size: 13))
                    .foregroundColor(on ? .white : .white.opacity(0.35))
                Text(label)
                    .font(.system(size: 9))
                    .foregroundColor(.white.opacity(0.5))
            }
            .frame(width: 44, height: 36)
            .background(on ? Color.zinc800 : Color.zinc800.opacity(0.5))
            .cornerRadius(6)
        }
        .buttonStyle(.plain)
    }
}

// MARK: - Remote video tile

#if canImport(LiveKit)
private struct RemoteVideoTile: View {
    @ObservedObject var participant: RemoteParticipant

    private var displayName: String {
        if let n = participant.name, !n.isEmpty { return n }
        if let id = participant.identity?.stringValue, !id.isEmpty { return id }
        return "Guest"
    }

    var body: some View {
        ZStack(alignment: .bottomLeading) {
            if let track = participant.firstCameraVideoTrack {
                SwiftUIVideoView(track, layoutMode: .fill)
                    .aspectRatio(16.0/9.0, contentMode: .fit)
                    .frame(maxWidth: .infinity, minHeight: 160, maxHeight: 240)
                    .cornerRadius(6)
                    .clipped()
            } else {
                ZStack {
                    Color.zinc800
                    Image(systemName: "person.fill")
                        .font(.system(size: 24))
                        .foregroundColor(.white.opacity(0.25))
                }
                .aspectRatio(16.0/9.0, contentMode: .fit)
                .frame(maxWidth: .infinity, minHeight: 160, maxHeight: 240)
                .cornerRadius(6)
            }
            Text(displayName)
                .font(.system(size: 9, weight: .medium))
                .foregroundColor(.white)
                .padding(.horizontal, 5)
                .padding(.vertical, 2)
                .background(Color.black.opacity(0.55))
                .cornerRadius(3)
                .padding(4)
        }
    }
}
#endif
