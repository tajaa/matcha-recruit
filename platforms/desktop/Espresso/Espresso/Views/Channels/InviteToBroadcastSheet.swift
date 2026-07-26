import SwiftUI

/// Owner-only sheet shown from the live broadcast panel toolbar. Lists
/// channel members and lets the owner promote any of them to publisher
/// (camera + mic on stage). Backend gate is owner-only at
/// `/channels/{id}/broadcast/promote`; we mirror that in the trigger by
/// only rendering the toolbar button for `isOwner`.
///
/// `publisherUserIds` is the live set from BroadcastService — already on
/// stage; rendering "Demote" instead of "Invite". The set updates via
/// `broadcast.publisher_changed` WS events fanning back into
/// BroadcastService, so the row state stays live without a refetch.
struct InviteToBroadcastSheet: View {
    let channelId: String
    let channelName: String
    let members: [ChannelMember]
    let myUserId: String

    @Environment(BroadcastService.self) private var broadcast: BroadcastService
    @Environment(\.dismiss) private var dismiss

    @State private var busyMemberId: String? = nil
    @State private var errorMessage: String? = nil

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider().opacity(0.3)
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
                Text("Invite to stage")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(.white)
                Text("#\(channelName) · \(broadcast.publisherUserIds.count) on stage")
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
                    Text("Invite people to the channel first to bring them on stage.")
                        .font(.system(size: 11))
                        .foregroundColor(.secondary)
                        .frame(maxWidth: .infinity, alignment: .center)
                        .padding(24)
                }
            }
        }
    }

    /// Already-on-stage publishers float to the top so the owner sees them
    /// first; everyone else sorts by name.
    private var sortedMembers: [ChannelMember] {
        let publishers = broadcast.publisherUserIds
        return members.sorted { a, b in
            let pa = publishers.contains(a.userId)
            let pb = publishers.contains(b.userId)
            if pa != pb { return pa && !pb }
            return a.name.localizedCaseInsensitiveCompare(b.name) == .orderedAscending
        }
    }

    private func row(member: ChannelMember) -> some View {
        let isMe = member.userId == myUserId
        let isPublisher = broadcast.publisherUserIds.contains(member.userId)
        let isBusy = busyMemberId == member.userId
        return HStack(spacing: 10) {
            avatar(member: member)
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 6) {
                    Text(member.name).font(.system(size: 12, weight: .medium)).foregroundColor(.white)
                    if isMe {
                        Text("(you)").font(.system(size: 10)).foregroundColor(.secondary)
                    }
                    if isPublisher {
                        Label("on stage", systemImage: "dot.radiowaves.left.and.right")
                            .labelStyle(.titleAndIcon)
                            .font(.system(size: 9, weight: .semibold))
                            .foregroundColor(Color.matcha500)
                            .padding(.horizontal, 5)
                            .padding(.vertical, 2)
                            .background(Color.matcha500.opacity(0.15))
                            .cornerRadius(3)
                    }
                }
                Text(member.email).font(.system(size: 10)).foregroundColor(.secondary)
            }
            Spacer()
            if isBusy {
                ProgressView().controlSize(.small)
            } else if isMe {
                // Owner is auto-publishing; no controls on own row.
                EmptyView()
            } else if isPublisher {
                Button("Remove") {
                    Task { await runDemote(member) }
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
                .tint(.red)
            } else {
                Button("Invite") {
                    Task { await runPromote(member) }
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

    private func runPromote(_ member: ChannelMember) async {
        busyMemberId = member.userId
        errorMessage = nil
        defer { busyMemberId = nil }
        do {
            try await broadcast.promote(userId: member.userId, channelId: channelId)
        } catch {
            errorMessage = "Invite failed: \(error.localizedDescription)"
        }
    }

    private func runDemote(_ member: ChannelMember) async {
        busyMemberId = member.userId
        errorMessage = nil
        defer { busyMemberId = nil }
        do {
            try await broadcast.demote(userId: member.userId, channelId: channelId)
        } catch {
            errorMessage = "Remove failed: \(error.localizedDescription)"
        }
    }
}
