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
    let isOwner: Bool

    @Environment(BroadcastService.self) private var broadcast: BroadcastService

    var body: some View {
        VStack(spacing: 0) {
            header
            videoGrid
            toolbar
        }
        .background(Color.black.opacity(0.85))
        .cornerRadius(8)
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .stroke(Color.matcha600.opacity(0.4), lineWidth: 1)
        )
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
    }

    // MARK: - Header

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

            Text(broadcast.isPublishing ? "You're on stage" : "Watching live")
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
        HStack {
            Spacer()
            VStack(spacing: 6) {
                Image(systemName: "waveform.circle")
                    .font(.system(size: 28))
                    .foregroundColor(Color.matcha500)
                Text("Audio broadcast")
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
        if let track = broadcast.room.localParticipant.firstCameraVideoTrack {
            ZStack(alignment: .bottomLeading) {
                SwiftUIVideoView(track,
                                layoutMode: .fill,
                                mirrorMode: .mirror)
                    .frame(height: 140)
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

                toolbarToggle(
                    on: broadcast.isCameraEnabled,
                    icon: broadcast.isCameraEnabled ? "video.fill" : "video.slash.fill",
                    label: "Camera"
                ) { broadcast.setCameraEnabled(!broadcast.isCameraEnabled) }
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
                    .frame(height: 140)
                    .cornerRadius(6)
                    .clipped()
            } else {
                ZStack {
                    Color.zinc800
                    Image(systemName: "person.fill")
                        .font(.system(size: 24))
                        .foregroundColor(.white.opacity(0.25))
                }
                .frame(height: 140)
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
