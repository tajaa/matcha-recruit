import SwiftUI

/// Owner-only sheet shown from the call panel toolbar. Lists channel members
/// and lets the owner invite them to the audio call. In invite-only mode an
/// invite grants join permission; in members mode it's just a nudge (the
/// member could join anyway). Backend gate is owner-only at
/// `/channels/{id}/call/invite`; we mirror that by only rendering the
/// trigger for `isOwner`.
///
/// Row state comes from CallService.activeCalls[channelId]:
/// `participantIds` (live occupancy via call.participants_changed WS events)
/// and `invitedUserIds` (hydrated by REST status + optimistic invite updates).
struct InviteToCallSheet: View {
    let channelId: String
    let channelName: String
    let members: [ChannelMember]
    let myUserId: String

    @Environment(CallService.self) private var call: CallService
    @Environment(\.dismiss) private var dismiss

    @State private var busyMemberId: String? = nil
    @State private var errorMessage: String? = nil

    private var info: ActiveCallInfo? { call.activeCalls[channelId] }
    private var inCallIds: Set<String> { Set(info?.participantIds ?? []) }
    private var invitedIds: Set<String> { Set(info?.invitedUserIds ?? []) }
    private var isFull: Bool { inCallIds.count >= call.maxParticipants }

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider().opacity(0.3)
            if isFull {
                Text("Call is full (\(call.maxParticipants)/\(call.maxParticipants)). Invited members can join once a spot frees up.")
                    .font(.system(size: 10))
                    .foregroundColor(.orange.opacity(0.9))
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 6)
                Divider().opacity(0.3)
            }
            list
            if let errorMessage {
                Divider().opacity(0.3)
                Text(errorMessage)
                    .font(.system(size: 11))
                    .foregroundColor(.red.opacity(0.85))
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(12)
            }
        }
        .frame(width: 380, height: 460)
        .background(Color.appBackground)
    }

    // MARK: - Header

    private var header: some View {
        HStack {
            VStack(alignment: .leading, spacing: 1) {
                Text("Invite to call")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(.white)
                Text("#\(channelName) · \(inCallIds.count)/\(call.maxParticipants) in call")
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
            }
            Spacer()
            Button("Done") { dismiss() }
                .buttonStyle(.plain)
                .font(.system(size: 12))
                .foregroundColor(.secondary)
        }
        .padding(14)
    }

    // MARK: - List

    private var list: some View {
        ScrollView {
            LazyVStack(spacing: 0) {
                ForEach(sortedMembers) { member in
                    row(member: member)
                    Divider().opacity(0.1)
                }
                if members.isEmpty {
                    Text("Invite people to the channel first to bring them into a call.")
                        .font(.system(size: 11))
                        .foregroundColor(.secondary)
                        .frame(maxWidth: .infinity, alignment: .center)
                        .padding(24)
                }
            }
        }
    }

    /// In-call members float to the top, then invited, then everyone by name.
    private var sortedMembers: [ChannelMember] {
        members.sorted { a, b in
            func rank(_ m: ChannelMember) -> Int {
                if inCallIds.contains(m.userId) { return 0 }
                if invitedIds.contains(m.userId) { return 1 }
                return 2
            }
            let ra = rank(a), rb = rank(b)
            if ra != rb { return ra < rb }
            return a.name.localizedCaseInsensitiveCompare(b.name) == .orderedAscending
        }
    }

    private func row(member: ChannelMember) -> some View {
        let isMe = member.userId == myUserId
        let isInCall = inCallIds.contains(member.userId)
        let isInvited = invitedIds.contains(member.userId)
        let isBusy = busyMemberId == member.userId
        return HStack(spacing: 10) {
            avatar(member: member)
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 6) {
                    Text(member.name).font(.system(size: 12, weight: .medium)).foregroundColor(.white)
                    if isMe {
                        Text("(you)").font(.system(size: 10)).foregroundColor(.secondary)
                    }
                    if isInCall {
                        Label("in call", systemImage: "waveform")
                            .labelStyle(.titleAndIcon)
                            .font(.system(size: 9, weight: .semibold))
                            .foregroundColor(Color.matcha500)
                            .padding(.horizontal, 5)
                            .padding(.vertical, 2)
                            .background(Color.matcha500.opacity(0.15))
                            .cornerRadius(3)
                    } else if isInvited {
                        Text("invited")
                            .font(.system(size: 9, weight: .semibold))
                            .foregroundColor(.secondary)
                            .padding(.horizontal, 5)
                            .padding(.vertical, 2)
                            .background(Color.white.opacity(0.08))
                            .cornerRadius(3)
                    }
                }
                Text(member.email).font(.system(size: 10)).foregroundColor(.secondary)
            }
            Spacer()
            if isBusy {
                ProgressView().controlSize(.small)
            } else if isMe || isInCall {
                EmptyView()
            } else if isInvited {
                Button("Re-invite") {
                    Task { await runInvite(member) }
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
            } else {
                Button("Invite") {
                    Task { await runInvite(member) }
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.small)
                .tint(Color.matcha600)
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 8)
    }

    private func avatar(member: ChannelMember) -> some View {
        ZStack {
            Circle().fill(Color.matcha500.opacity(0.4)).frame(width: 28, height: 28)
            Text(String(member.name.prefix(1)).uppercased())
                .font(.system(size: 11, weight: .bold))
                .foregroundColor(.white)
        }
    }

    // MARK: - Actions

    private func runInvite(_ member: ChannelMember) async {
        busyMemberId = member.userId
        errorMessage = nil
        defer { busyMemberId = nil }
        do {
            try await call.invite(userIds: [member.userId], channelId: channelId)
        } catch {
            errorMessage = "Invite failed: \(error.localizedDescription)"
        }
    }
}
