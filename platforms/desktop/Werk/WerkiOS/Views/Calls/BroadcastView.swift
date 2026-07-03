import SwiftUI
#if canImport(LiveKit)
import LiveKit
#endif

/// Full-screen live video broadcast. Viewers watch publisher camera feeds; the
/// owner (and promoted publishers) can toggle camera/mic and end. Reuses the
/// shared `BroadcastService` verbatim.
struct BroadcastView: View {
    let channelName: String
    let members: [ChannelMember]
    @Environment(BroadcastService.self) private var broadcast
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(spacing: 0) {
            header
            stage
            controls
        }
        .background(Color.black.ignoresSafeArea())
        .preferredColorScheme(.dark)
        .onChange(of: broadcast.isConnected) { _, connected in
            if !connected { dismiss() }
        }
    }

    private var header: some View {
        HStack(spacing: 8) {
            Text("LIVE").font(.caption.bold()).foregroundStyle(.white)
                .padding(.horizontal, 6).padding(.vertical, 2)
                .background(.red, in: Capsule())
            Text(channelName).font(.subheadline).foregroundStyle(.white)
            Spacer()
            Text(elapsed).font(.caption.monospacedDigit()).foregroundStyle(.white.opacity(0.7))
        }
        .padding()
    }

    @ViewBuilder
    private var stage: some View {
        #if canImport(LiveKit)
        let _ = broadcast.participantTick
        let publishers = Array(broadcast.room.remoteParticipants.values).filter { $0.firstCameraVideoTrack != nil }
        ScrollView {
            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 8) {
                if broadcast.isPublishing { localTile }
                ForEach(publishers, id: \.identity) { p in
                    RemoteVideoTile(participant: p, name: name(forId: p.identity?.stringValue))
                }
            }
            .padding(8)
            if publishers.isEmpty && !broadcast.isPublishing {
                ContentUnavailableView("Waiting for video", systemImage: "video.slash")
                    .foregroundStyle(.white.opacity(0.6))
                    .padding(.top, 60)
            }
        }
        #else
        Spacer()
        Image(systemName: "video.circle").font(.system(size: 60)).foregroundStyle(.white.opacity(0.5))
        Spacer()
        #endif
    }

    #if canImport(LiveKit)
    @ViewBuilder
    private var localTile: some View {
        ZStack(alignment: .bottomLeading) {
            if let pub = broadcast.room.localParticipant.firstCameraPublication,
               let track = pub.track as? VideoTrack {
                SwiftUIVideoView(track, layoutMode: .fill, mirrorMode: .mirror)
            } else {
                Color.black.overlay(Image(systemName: "mic.fill").foregroundStyle(.white))
            }
            Text("You").font(.caption2).foregroundStyle(.white)
                .padding(4).background(.black.opacity(0.5), in: Capsule()).padding(6)
        }
        .aspectRatio(3.0/4.0, contentMode: .fit)
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }
    #endif

    private var controls: some View {
        HStack(spacing: 24) {
            if broadcast.isPublishing {
                circle(broadcast.isMicEnabled ? "mic.fill" : "mic.slash.fill",
                       bg: .white.opacity(0.12)) { broadcast.setMicEnabled(!broadcast.isMicEnabled) }
                circle(broadcast.isCameraEnabled ? "video.fill" : "video.slash.fill",
                       bg: .white.opacity(0.12)) { broadcast.setCameraEnabled(!broadcast.isCameraEnabled) }
            }
            if broadcast.isOwner {
                circle("stop.fill", bg: .red) { Task { await broadcast.stopBroadcast() } }
            } else {
                circle("xmark", bg: .white.opacity(0.12)) { Task { await broadcast.leave() } }
            }
        }
        .padding(.vertical, 24)
    }

    private func circle(_ icon: String, bg: Color, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: icon).font(.system(size: 22)).foregroundStyle(.white)
                .frame(width: 60, height: 60).background(bg, in: Circle())
        }
    }

    private var elapsed: String {
        String(format: "%d:%02d", broadcast.elapsedSeconds / 60, broadcast.elapsedSeconds % 60)
    }

    private func name(forId id: String?) -> String {
        guard let id, let m = members.first(where: { $0.userId == id }) else { return "Guest" }
        return m.name
    }
}

#if canImport(LiveKit)
/// A remote publisher's video tile. `@ObservedObject` on the LiveKit participant
/// so the tile re-renders when its track (un)publishes.
private struct RemoteVideoTile: View {
    @ObservedObject var participant: RemoteParticipant
    let name: String

    var body: some View {
        ZStack(alignment: .bottomLeading) {
            if let track = participant.firstCameraVideoTrack {
                SwiftUIVideoView(track, layoutMode: .fill)
            } else {
                Color.black
            }
            Text(name).font(.caption2).foregroundStyle(.white)
                .padding(4).background(.black.opacity(0.5), in: Capsule()).padding(6)
        }
        .aspectRatio(3.0/4.0, contentMode: .fit)
        .clipShape(RoundedRectangle(cornerRadius: 10))
    }
}
#endif
