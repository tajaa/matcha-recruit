/// CallPanelView — audio-call panel shown above chat when this client is
/// connected to the channel's call. Parallel to BroadcastPanelView but
/// audio-only: participant rows with speaking indicators instead of a video
/// grid. Falls back to a static banner when the LiveKit SDK is not linked.

import SwiftUI

#if canImport(LiveKit)
import LiveKit
#endif

struct CallPanelView: View {
    let channelId: String
    let channelName: String
    let isOwner: Bool
    /// Channel members — used to resolve display names by identity and to
    /// feed the invite sheet without a refetch.
    let members: [ChannelMember]
    let myUserId: String

    @Environment(CallService.self) private var call: CallService
    @State private var showInviteSheet = false
    /// Collapsed state shows only the header strip so chat fills the pane.
    /// Persists per-channel, same pattern as the broadcast panel.
    @AppStorage private var collapsed: Bool

    init(channelId: String, channelName: String, isOwner: Bool, members: [ChannelMember], myUserId: String) {
        self.channelId = channelId
        self.channelName = channelName
        self.isOwner = isOwner
        self.members = members
        self.myUserId = myUserId
        self._collapsed = AppStorage(wrappedValue: false, "mw-call-collapsed:\(channelId)")
    }

    private var participantCount: Int {
        #if canImport(LiveKit)
        return call.room.remoteParticipants.count + 1
        #else
        return 1
        #endif
    }

    var body: some View {
        VStack(spacing: 0) {
            header
            if !collapsed {
                participantRows
                if let err = call.errorMessage {
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
        .sheet(isPresented: $showInviteSheet) {
            InviteToCallSheet(
                channelId: channelId,
                channelName: channelName,
                members: members,
                myUserId: myUserId,
            )
            .environment(call)
        }
    }

    // MARK: - Header

    private var header: some View {
        HStack(spacing: 8) {
            Text("CALL")
                .font(.system(size: 9, weight: .bold))
                .foregroundColor(.white)
                .padding(.horizontal, 6)
                .padding(.vertical, 2)
                .background(Color.matcha600)
                .cornerRadius(3)

            Text("Audio call · \(participantCount)/\(call.maxParticipants)")
                .font(.system(size: 11))
                .foregroundColor(.white.opacity(0.75))

            if call.mode == .inviteOnly {
                Text("invite only")
                    .font(.system(size: 9, weight: .medium))
                    .foregroundColor(.white.opacity(0.45))
                    .padding(.horizontal, 5)
                    .padding(.vertical, 2)
                    .background(Color.white.opacity(0.08))
                    .cornerRadius(3)
            }

            let mins = call.elapsedSeconds / 60
            let secs = call.elapsedSeconds % 60
            Text(String(format: "%d:%02d", mins, secs))
                .font(.system(size: 10, weight: .medium, design: .monospaced))
                .foregroundColor(.white.opacity(0.6))

            Spacer()

            Button {
                collapsed.toggle()
            } label: {
                Image(systemName: collapsed ? "chevron.down" : "chevron.up")
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundColor(.white.opacity(0.7))
                    .frame(width: 18, height: 18)
            }
            .buttonStyle(.plain)
            .help(collapsed ? "Expand call" : "Minimize to focus on chat")
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
    }

    // MARK: - Participant rows

    @ViewBuilder
    private var participantRows: some View {
        #if canImport(LiveKit)
        let _ = call.participantTick  // observe ticks for re-render
        VStack(spacing: 0) {
            participantRow(
                name: "You",
                isSpeaking: call.room.localParticipant.isSpeaking,
                isMuted: !call.isMicEnabled
            )
            ForEach(Array(call.room.remoteParticipants.values), id: \.identity) { participant in
                participantRow(
                    name: displayName(for: participant),
                    isSpeaking: participant.isSpeaking,
                    isMuted: false
                )
            }
        }
        .padding(.horizontal, 8)
        .padding(.bottom, 4)
        #else
        HStack {
            Spacer()
            VStack(spacing: 6) {
                Image(systemName: "waveform.circle")
                    .font(.system(size: 28))
                    .foregroundColor(Color.matcha500)
                Text("Audio call")
                    .font(.system(size: 11))
                    .foregroundColor(.white.opacity(0.5))
            }
            Spacer()
        }
        .frame(height: 80)
        #endif
    }

    #if canImport(LiveKit)
    private func displayName(for participant: RemoteParticipant) -> String {
        if let n = participant.name, !n.isEmpty { return n }
        if let id = participant.identity?.stringValue,
           let member = members.first(where: { $0.userId == id }) {
            return member.name
        }
        return "Guest"
    }
    #endif

    private func participantRow(name: String, isSpeaking: Bool, isMuted: Bool) -> some View {
        HStack(spacing: 10) {
            ZStack {
                Circle()
                    .fill(Color.matcha500.opacity(0.4))
                    .frame(width: 26, height: 26)
                Text(String(name.prefix(1)).uppercased())
                    .font(.system(size: 10, weight: .bold))
                    .foregroundColor(.white)
            }
            .overlay(
                Circle().stroke(
                    isSpeaking ? Color.matcha500 : Color.clear, lineWidth: 2
                )
            )
            Text(name)
                .font(.system(size: 12, weight: .medium))
                .foregroundColor(.white)
            if isMuted {
                Image(systemName: "mic.slash.fill")
                    .font(.system(size: 9))
                    .foregroundColor(.white.opacity(0.4))
            }
            Spacer()
            Image(systemName: "waveform")
                .font(.system(size: 11))
                .foregroundColor(isSpeaking ? Color.matcha500 : .white.opacity(0.15))
        }
        .padding(.horizontal, 6)
        .padding(.vertical, 5)
    }

    // MARK: - Toolbar

    private var toolbar: some View {
        HStack(spacing: 12) {
            Button {
                call.setMicEnabled(!call.isMicEnabled)
            } label: {
                VStack(spacing: 2) {
                    Image(systemName: call.isMicEnabled ? "mic.fill" : "mic.slash.fill")
                        .font(.system(size: 13))
                        .foregroundColor(call.isMicEnabled ? .white : .white.opacity(0.35))
                    Text("Mic")
                        .font(.system(size: 9))
                        .foregroundColor(.white.opacity(0.5))
                }
                .frame(width: 44, height: 36)
                .background(call.isMicEnabled ? Color.zinc800 : Color.zinc800.opacity(0.5))
                .cornerRadius(6)
            }
            .buttonStyle(.plain)

            if isOwner {
                Button {
                    showInviteSheet = true
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
                .disabled(participantCount >= call.maxParticipants)
                .help(participantCount >= call.maxParticipants
                      ? "Call is full (\(call.maxParticipants)/\(call.maxParticipants))"
                      : "Invite channel members to the call")
            }

            Spacer()

            if isOwner {
                Button(role: .destructive) {
                    Task { await call.stopCall() }
                } label: {
                    HStack(spacing: 4) {
                        Image(systemName: "stop.circle").font(.system(size: 10))
                        Text("End call").font(.system(size: 11, weight: .medium))
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
                    Task { await call.leave() }
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
}
