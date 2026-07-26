import SwiftUI

/// Member moderation sheet — werk port of the web client's `ChannelView`
/// member-management UI. Members see a read-only list; channel owners and
/// moderators see a per-row "..." menu with role-gated actions.
///
/// The sheet does not subscribe to the channel WebSocket — the server only
/// broadcasts message_deleted, not role changes / kicks / transfers — so
/// every successful action calls `onChanged()` to let the parent refetch
/// the channel detail and re-render members.
struct ManageMembersSheet: View {
    let channelId: String
    let channelName: String
    let members: [ChannelMember]
    let myUserId: String
    let myRole: String
    /// Global admin role (`appState.currentUser?.role == "admin"`). Treated
    /// as moderator-on-anything except dethroning the existing owner.
    let isGlobalAdmin: Bool
    let onChanged: () -> Void

    @Environment(\.dismiss) private var dismiss

    @State private var pendingKick: ChannelMember? = nil
    @State private var pendingTransfer: ChannelMember? = nil
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
        .frame(width: 420, height: 480)
        .background(Color.appBackground)
        .confirmationDialog(
            "Remove from #\(channelName)?",
            isPresented: kickBinding,
            presenting: pendingKick,
        ) { member in
            Button("Remove \(member.name)", role: .destructive) {
                Task { await runKick(member) }
            }
            Button("Cancel", role: .cancel) { pendingKick = nil }
        } message: { member in
            Text("\(member.name) will lose access to this channel. They can rejoin if the channel is public.")
        }
        .confirmationDialog(
            "Transfer ownership?",
            isPresented: transferBinding,
            presenting: pendingTransfer,
        ) { member in
            Button("Transfer to \(member.name)", role: .destructive) {
                Task { await runTransfer(member) }
            }
            Button("Cancel", role: .cancel) { pendingTransfer = nil }
        } message: { member in
            Text("You will become a moderator. \(member.name) will become the channel owner. This cannot be undone.")
        }
    }

    // MARK: - Header

    private var header: some View {
        HStack {
            VStack(alignment: .leading, spacing: 1) {
                Text("Members")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(.white)
                Text("#\(channelName) · \(members.count)")
                    .font(.system(size: 10))
                    .foregroundColor(.secondary)
            }
            Spacer()
            Button("Close") { dismiss() }
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
            }
        }
    }

    private var sortedMembers: [ChannelMember] {
        // Owner first, then mods, then members. Stable inside each bucket.
        members.sorted { a, b in
            let oa = roleOrder(a.channelRole)
            let ob = roleOrder(b.channelRole)
            if oa != ob { return oa < ob }
            return a.name.localizedCaseInsensitiveCompare(b.name) == .orderedAscending
        }
    }

    private func roleOrder(_ role: String) -> Int {
        switch role {
        case "owner": return 0
        case "moderator": return 1
        default: return 2
        }
    }

    private func row(member: ChannelMember) -> some View {
        let isMe = member.userId == myUserId
        let canMod = canModerate(target: member)
        let isBusy = busyMemberId == member.userId
        return HStack(spacing: 10) {
            avatar(member: member)
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 6) {
                    Text(member.name).font(.system(size: 12, weight: .medium)).foregroundColor(.white)
                    if isMe {
                        Text("(you)").font(.system(size: 10)).foregroundColor(.secondary)
                    }
                    roleBadge(channelRole: member.channelRole)
                }
                Text(member.email).font(.system(size: 10)).foregroundColor(.secondary)
            }
            Spacer()
            if isBusy {
                ProgressView().controlSize(.small)
            } else if canMod {
                rowMenu(member: member)
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

    @ViewBuilder
    private func roleBadge(channelRole: String) -> some View {
        switch channelRole {
        case "owner":
            HStack(spacing: 3) {
                Image(systemName: "crown.fill").font(.system(size: 8))
                Text("owner").font(.system(size: 9, weight: .semibold))
            }
            .foregroundColor(Color.orange.opacity(0.9))
            .padding(.horizontal, 5)
            .padding(.vertical, 2)
            .background(Color.orange.opacity(0.15))
            .cornerRadius(3)
        case "moderator":
            HStack(spacing: 3) {
                Image(systemName: "shield.fill").font(.system(size: 8))
                Text("mod").font(.system(size: 9, weight: .semibold))
            }
            .foregroundColor(Color.blue.opacity(0.9))
            .padding(.horizontal, 5)
            .padding(.vertical, 2)
            .background(Color.blue.opacity(0.15))
            .cornerRadius(3)
        default:
            EmptyView()
        }
    }

    private func rowMenu(member: ChannelMember) -> some View {
        Menu {
            // Promote to moderator (owner-only path; UI hides for moderators).
            if myRole == "owner" || isGlobalAdmin {
                if member.channelRole == "member" {
                    Button {
                        Task { await runSetRole(member, role: .moderator) }
                    } label: { Label("Promote to moderator", systemImage: "shield") }
                }
                if member.channelRole == "moderator" {
                    Button {
                        Task { await runSetRole(member, role: .member) }
                    } label: { Label("Demote to member", systemImage: "shield.slash") }
                    Button {
                        pendingTransfer = member
                    } label: { Label("Transfer ownership…", systemImage: "crown") }
                }
                Divider()
            }
            Button(role: .destructive) {
                pendingKick = member
            } label: { Label("Remove from channel…", systemImage: "person.fill.xmark") }
        } label: {
            Image(systemName: "ellipsis")
                .font(.system(size: 13, weight: .semibold))
                .foregroundColor(.white.opacity(0.6))
                .padding(.horizontal, 6)
                .padding(.vertical, 2)
        }
        .menuStyle(.borderlessButton)
        .menuIndicator(.hidden)
        .fixedSize()
    }

    // MARK: - Gates

    /// Mirrors the web ChannelView `canManage` logic.
    private func canModerate(target: ChannelMember) -> Bool {
        if target.userId == myUserId { return false }
        if isGlobalAdmin { return target.channelRole != "owner" || myRole == "owner" }
        if myRole == "owner" { return target.channelRole != "owner" }
        if myRole == "moderator" { return target.channelRole == "member" }
        return false
    }

    private var kickBinding: Binding<Bool> {
        Binding(get: { pendingKick != nil }, set: { if !$0 { pendingKick = nil } })
    }

    private var transferBinding: Binding<Bool> {
        Binding(get: { pendingTransfer != nil }, set: { if !$0 { pendingTransfer = nil } })
    }

    // MARK: - Actions

    private func runSetRole(_ member: ChannelMember, role: ChannelsService.ManageableRole) async {
        busyMemberId = member.userId
        errorMessage = nil
        defer { busyMemberId = nil }
        do {
            try await ChannelsService.shared.setMemberRole(
                channelId: channelId, userId: member.userId, role: role,
            )
            onChanged()
        } catch {
            errorMessage = "Role change failed: \(error.localizedDescription)"
        }
    }

    private func runKick(_ member: ChannelMember) async {
        pendingKick = nil
        busyMemberId = member.userId
        errorMessage = nil
        defer { busyMemberId = nil }
        do {
            try await ChannelsService.shared.kickMember(
                channelId: channelId, userId: member.userId,
            )
            onChanged()
        } catch {
            errorMessage = "Remove failed: \(error.localizedDescription)"
        }
    }

    private func runTransfer(_ member: ChannelMember) async {
        pendingTransfer = nil
        busyMemberId = member.userId
        errorMessage = nil
        defer { busyMemberId = nil }
        do {
            try await ChannelsService.shared.transferOwnership(
                channelId: channelId, newOwnerId: member.userId,
            )
            onChanged()
        } catch {
            errorMessage = "Transfer failed: \(error.localizedDescription)"
        }
    }
}
