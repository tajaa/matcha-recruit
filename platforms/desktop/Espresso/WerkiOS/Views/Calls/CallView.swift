import SwiftUI
#if canImport(LiveKit)
import LiveKit
#endif

/// Full-screen audio-call UI for the channel's active call. Reuses the shared
/// `CallService` (LiveKit wrapper) verbatim — participant rows with speaking
/// rings, mic toggle, and leave/end. Dismisses itself when the call ends.
struct CallView: View {
    let channelName: String
    let members: [ChannelMember]
    @Environment(CallService.self) private var call
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(spacing: 0) {
            header
            ScrollView { participants.padding(.top, 12) }
            controls
        }
        .background(Color.black.ignoresSafeArea())
        .preferredColorScheme(.dark)
        .onChange(of: call.isConnected) { _, connected in
            if !connected { dismiss() }
        }
    }

    private var header: some View {
        VStack(spacing: 4) {
            Text(channelName).font(.headline).foregroundStyle(.white)
            HStack(spacing: 8) {
                Label("\(participantCount)/\(call.maxParticipants)", systemImage: "person.2.fill")
                Text(elapsed).monospacedDigit()
                if call.mode == .inviteOnly {
                    Text("invite only").padding(.horizontal, 6).padding(.vertical, 2)
                        .background(.white.opacity(0.12), in: Capsule())
                }
            }
            .font(.caption).foregroundStyle(.white.opacity(0.7))
        }
        .padding(.top, 24).padding(.bottom, 12)
    }

    @ViewBuilder
    private var participants: some View {
        #if canImport(LiveKit)
        let _ = call.participantTick   // re-render on participant/speaker change
        VStack(spacing: 10) {
            participantRow(name: "You", speaking: call.room.localParticipant.isSpeaking, muted: !call.isMicEnabled)
            ForEach(Array(call.room.remoteParticipants.values), id: \.identity) { p in
                participantRow(name: name(for: p), speaking: p.isSpeaking, muted: false)
            }
        }
        .padding(.horizontal, 20)
        #else
        Image(systemName: "waveform.circle").font(.system(size: 60)).foregroundStyle(.white.opacity(0.5))
        #endif
    }

    private func participantRow(name: String, speaking: Bool, muted: Bool) -> some View {
        HStack(spacing: 14) {
            Avatar(url: nil, name: name, size: 52)
                .overlay(Circle().stroke(Color.green, lineWidth: speaking ? 3 : 0))
            Text(name).font(.title3.weight(.medium)).foregroundStyle(.white)
            Spacer()
            Image(systemName: muted ? "mic.slash.fill" : "waveform")
                .foregroundStyle(muted ? .white.opacity(0.4) : (speaking ? .green : .white.opacity(0.3)))
        }
        .padding(.vertical, 6)
    }

    private var controls: some View {
        HStack(spacing: 28) {
            circleButton(call.isMicEnabled ? "mic.fill" : "mic.slash.fill",
                         tint: call.isMicEnabled ? .white : .red,
                         bg: .white.opacity(0.12)) {
                call.setMicEnabled(!call.isMicEnabled)
            }
            if call.isOwner {
                circleButton("phone.down.fill", tint: .white, bg: .red) {
                    Task { await call.stopCall() }
                }
            } else {
                circleButton("phone.down.fill", tint: .white, bg: .red) {
                    Task { await call.leave() }
                }
            }
        }
        .padding(.vertical, 28)
    }

    private func circleButton(_ icon: String, tint: Color, bg: Color, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: icon)
                .font(.system(size: 24))
                .foregroundStyle(tint)
                .frame(width: 64, height: 64)
                .background(bg, in: Circle())
        }
    }

    private var participantCount: Int {
        #if canImport(LiveKit)
        return call.room.remoteParticipants.count + 1
        #else
        return 1
        #endif
    }

    private var elapsed: String {
        String(format: "%d:%02d", call.elapsedSeconds / 60, call.elapsedSeconds % 60)
    }

    #if canImport(LiveKit)
    private func name(for participant: RemoteParticipant) -> String {
        if let n = participant.name, !n.isEmpty { return n }
        if let id = participant.identity?.stringValue,
           let m = members.first(where: { $0.userId == id }) {
            return m.name
        }
        return "Guest"
    }
    #endif
}
