import SwiftUI

// MARK: - Channels hub (full-pane dashboard)

/// Full-pane "Channels" hub — opened from the sidebar Channels nav row. Lists
/// the channels you're in; filter (Starred / Mine), create, and browse-public
/// live here. Picking a card sets `selectedChannelId` so the channel opens over
/// the hub.
///
/// Split out of ChannelsSidebarView.swift, which owned three unrelated
/// top-level views.
struct ChannelsLibraryView: View {
    @Environment(AppState.self) private var appState

    @State private var channels: [ChannelSummary] = []
    /// Public channels the user could join (GET /channels/discover —
    /// already excludes memberships). Third hub section.
    @State private var discover: [ChannelSummary] = []
    @State private var isLoading = true
    @State private var search = ""
    @State private var showCreate = false
    @State private var starGen = 0
    @State private var railSearch = ""
    @State private var railCollapsed = false
    /// Channel id with a join request in flight (spinner on that card).
    @State private var joiningId: String?

    private let columns = [GridItem(.adaptive(minimum: 220, maximum: 300), spacing: 14)]

    var body: some View {
        HSplitView {
            if railCollapsed {
                MWHubRailStrip { railCollapsed = false }
            } else {
                rail.frame(minWidth: 232, idealWidth: 258, maxWidth: 320)
            }
            Group {
                if let id = appState.selectedChannelId {
                    ChannelDetailView(channelId: id)
                } else {
                    VStack(spacing: 0) {
                        header
                        Divider().background(appState.themeBorder)
                        content
                    }
                    .background(ThemeRadialBackground())
                }
            }
            .frame(minWidth: 420, maxWidth: .infinity, maxHeight: .infinity)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .task { await load() }
        .onChange(of: appState.channelsListGeneration) { _, _ in Task { await load() } }
        .sheet(isPresented: $showCreate) {
            CreateChannelSheet { ch in
                appState.channelsListGeneration &+= 1
                open(ch.id)
            }
        }
    }

    // ── Rail ────────────────────────────────────────────────────────────
    private var railChannels: [ChannelSummary] {
        _ = starGen
        var out = channels.filter { $0.isMember }
        if !railSearch.isEmpty { out = out.filter { $0.name.localizedCaseInsensitiveContains(railSearch) } }
        return out.sortedStarredFirst()
    }

    private var rail: some View {
        MWHubRail {
            VStack(spacing: 8) {
                HStack {
                    Text("Channels").font(.system(size: 12, weight: .semibold)).foregroundColor(appState.themeTextSecondary)
                    Spacer()
                    MWHubRailIconButton(icon: "sidebar.left", help: "Hide sidebar") { railCollapsed = true }
                    MWHubRailIconButton(icon: "magnifyingglass", help: "Browse") { browse() }
                    MWHubRailIconButton(icon: "plus", help: "New channel") { showCreate = true }
                }
                HStack(spacing: 6) {
                    Image(systemName: "line.3.horizontal.decrease").font(.system(size: 10)).foregroundColor(appState.themeTextSecondary)
                    TextField("Filter", text: $railSearch).textFieldStyle(.plain)
                        .font(.system(size: 11)).foregroundColor(appState.themeText)
                }
                .padding(.horizontal, 8).padding(.vertical, 5)
                .background(Capsule().fill(appState.themeText.opacity(0.06)))
            }
        } rows: {
            MWHubRailRow(icon: "square.grid.2x2", title: "All Channels",
                         selected: appState.selectedChannelId == nil) {
                appState.selectedChannelId = nil
            }
            ForEach(railChannels) { c in
                let starred = ChannelStarStore.shared.isStarred(c.id)
                // Crown marks channels you run, so yours read at a glance.
                MWHubRailRow(icon: starred ? "star.fill" : (c.myRole == "owner" ? "crown" : "number"),
                             title: c.name,
                             selected: appState.selectedChannelId == c.id,
                             accent: starred,
                             trailing: c.unreadCount > 0 ? "\(min(c.unreadCount, 99))" : nil) { open(c.id) }
                    .contextMenu {
                        Button(starred ? "Unstar" : "Star") { ChannelStarStore.shared.toggle(c.id); starGen += 1 }
                        Divider()
                        AuxOpenMenuButtons(target: .channel(c.id))
                    }
            }
        }
    }

    // ── Sections — the three kinds of channels ──────────────────────────
    // "Yours" = channels you own; "Joined" = member but someone else runs it;
    // "Open to join" = public channels from /discover you're not in yet.

    private func searched(_ list: [ChannelSummary]) -> [ChannelSummary] {
        guard !search.isEmpty else { return list }
        return list.filter {
            $0.name.localizedCaseInsensitiveContains(search)
                || ($0.description?.localizedCaseInsensitiveContains(search) ?? false)
        }
    }

    private func sortedByStar(_ list: [ChannelSummary]) -> [ChannelSummary] {
        _ = starGen
        return list.sortedStarredFirst()
    }

    private var mineChannels: [ChannelSummary] {
        sortedByStar(searched(channels.filter { $0.isMember && $0.myRole == "owner" }))
    }

    private var joinedChannels: [ChannelSummary] {
        sortedByStar(searched(channels.filter { $0.isMember && $0.myRole != "owner" }))
    }

    private var joinableChannels: [ChannelSummary] {
        searched(discover)
    }

    private var header: some View {
        VStack(spacing: 12) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Channels").font(.system(size: 20, weight: .bold)).foregroundColor(appState.themeText)
                    Text("Team spaces and real-time conversations")
                        .font(.system(size: 12)).foregroundColor(appState.themeTextSecondary)
                }
                Spacer()
                Button { browse() } label: {
                    HStack(spacing: 5) { Image(systemName: "magnifyingglass"); Text("Browse").font(.system(size: 12, weight: .semibold)) }
                        .padding(.horizontal, 12).padding(.vertical, 7)
                        .background(appState.themeAccent.opacity(0.10)).foregroundColor(appState.themeAccent).cornerRadius(8)
                }
                .buttonStyle(.plain)
                Button { showCreate = true } label: {
                    HStack(spacing: 5) { Image(systemName: "plus"); Text("New Channel").font(.system(size: 12, weight: .semibold)) }
                        .padding(.horizontal, 12).padding(.vertical, 7)
                        .background(appState.themeAccent).foregroundColor(appState.themeOnAccent).cornerRadius(8)
                }
                .buttonStyle(.plain)
            }
            HStack(spacing: 8) {
                Spacer()
                MWHubSearch(text: $search)
            }
        }
        .padding(20)
    }

    @ViewBuilder private var content: some View {
        if isLoading {
            Spacer(); ProgressView().tint(appState.themeTextSecondary); Spacer()
        } else if mineChannels.isEmpty && joinedChannels.isEmpty && joinableChannels.isEmpty {
            MWHubEmpty(icon: "number",
                       title: search.isEmpty ? "No channels yet" : "No channels match",
                       cta: "New Channel") { showCreate = true }
        } else {
            ScrollView {
                VStack(alignment: .leading, spacing: 22) {
                    section(title: "Started by you", icon: "crown.fill",
                            subtitle: "Channels you run", items: mineChannels, joinable: false)
                    section(title: "Joined", icon: "person.2.fill",
                            subtitle: "Channels run by others", items: joinedChannels, joinable: false)
                    section(title: "Open to join", icon: "sparkles",
                            subtitle: "Public channels from the community", items: joinableChannels, joinable: true)
                }
                .padding(20)
            }
        }
    }

    @ViewBuilder
    private func section(title: String, icon: String, subtitle: String,
                         items: [ChannelSummary], joinable: Bool) -> some View {
        if !items.isEmpty {
            VStack(alignment: .leading, spacing: 10) {
                HStack(spacing: 7) {
                    Image(systemName: icon)
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundColor(appState.themeAccent)
                    Text(title)
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundColor(appState.themeText)
                    Text("\(items.count)")
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundColor(appState.themeTextSecondary)
                        .padding(.horizontal, 6).padding(.vertical, 1)
                        .background(Capsule().fill(appState.themeText.opacity(0.07)))
                    Text(subtitle)
                        .font(.system(size: 11))
                        .foregroundColor(appState.themeTextSecondary)
                    Spacer()
                }
                LazyVGrid(columns: columns, spacing: 14) {
                    ForEach(items) { c in card(c, joinable: joinable) }
                }
            }
        }
    }

    private func card(_ c: ChannelSummary, joinable: Bool) -> some View {
        let starred = ChannelStarStore.shared.isStarred(c.id)
        let isMine = c.myRole == "owner"
        return Button {
            if joinable { join(c) } else { open(c.id) }
        } label: {
            VStack(alignment: .leading, spacing: 8) {
                cardFounderRow(c, isMine: isMine)
                HStack(spacing: 5) {
                    Image(systemName: starred ? "star.fill" : "number")
                        .font(.system(size: 12)).foregroundColor(starred ? appState.themeAccent : appState.themeTextSecondary)
                    Text(c.name).font(.system(size: 13, weight: .semibold)).foregroundColor(appState.themeText).lineLimit(1)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                if let d = c.description, !d.isEmpty {
                    Text(d).font(.system(size: 11)).foregroundColor(appState.themeTextSecondary).lineLimit(2)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                Spacer(minLength: 0)
                cardFooter(c, joinable: joinable)
            }
            .padding(14).frame(height: 132, alignment: .top)
            .background(RoundedRectangle(cornerRadius: 10).fill(appState.themeCard))
            .overlay(
                RoundedRectangle(cornerRadius: 10)
                    .stroke(isMine ? appState.themeAccent.opacity(0.35) : appState.themeBorder, lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
        .contextMenu {
            if !joinable {
                Button(starred ? "Unstar" : "Star") {
                    ChannelStarStore.shared.toggle(c.id); starGen += 1
                }
            }
        }
    }

    /// Founder row — who runs this channel, plus the paid/private/unread marks.
    private func cardFounderRow(_ c: ChannelSummary, isMine: Bool) -> some View {
        HStack(spacing: 7) {
            ChannelAvatarView(senderId: c.createdById ?? c.id,
                              payloadURL: c.createdByAvatarUrl,
                              name: c.createdByName ?? c.name,
                              size: 22)
            Text(isMine ? "Run by you" : "by \(c.createdByName ?? "Unknown")")
                .font(.system(size: 10, weight: .medium))
                .foregroundColor(isMine ? appState.themeAccent : appState.themeTextSecondary)
                .lineLimit(1)
            Spacer()
            if c.isPaid {
                Image(systemName: "dollarsign.circle.fill").font(.system(size: 10)).foregroundColor(appState.themeTextSecondary)
            }
            if c.visibility == "private" {
                Image(systemName: "lock.fill").font(.system(size: 9)).foregroundColor(appState.themeTextSecondary)
            }
            if c.unreadCount > 0 {
                Text("\(min(c.unreadCount, 99))")
                    .font(.system(size: 8, weight: .bold)).foregroundColor(appState.themeOnAccent)
                    .padding(.horizontal, 5).padding(.vertical, 1)
                    .background(Capsule().fill(appState.themeAccent))
            }
        }
    }

    /// Card footer: members · topic · join affordance.
    private func cardFooter(_ c: ChannelSummary, joinable: Bool) -> some View {
        HStack(spacing: 8) {
            HStack(spacing: 3) {
                Image(systemName: "person.2").font(.system(size: 9))
                Text("\(c.memberCount)").font(.system(size: 10, weight: .medium))
            }
            .foregroundColor(appState.themeTextSecondary)
            if let cat = c.category, !cat.isEmpty {
                Text(cat.capitalized)
                    .font(.system(size: 9, weight: .medium))
                    .foregroundColor(appState.themeTextSecondary)
                    .padding(.horizontal, 6).padding(.vertical, 2)
                    .background(Capsule().fill(appState.themeText.opacity(0.06)))
            }
            Spacer()
            if joinable {
                if joiningId == c.id {
                    ProgressView().controlSize(.mini)
                } else {
                    Text(c.isPaid ? "View" : "Join")
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundColor(appState.themeOnAccent)
                        .padding(.horizontal, 10).padding(.vertical, 3)
                        .background(Capsule().fill(appState.themeAccent))
                }
            }
        }
    }

    // ── Actions ─────────────────────────────────────────────────────────

    /// Free public channel → join inline and open it. Paid → route to the
    /// Browse surface, which owns the subscribe flow.
    private func join(_ c: ChannelSummary) {
        if c.isPaid { browse(); return }
        guard joiningId == nil else { return }
        joiningId = c.id
        Task {
            defer { joiningId = nil }
            do {
                try await ChannelsService.shared.joinChannel(id: c.id)
                await load()
                open(c.id)
            } catch {
                print("[ChannelsHub] join failed: \(error)")
            }
        }
    }

    private func open(_ id: String) {
        appState.selectedChannelId = id   // hub flag stays set → back returns here
        appState.selectedThreadId = nil; appState.selectedProjectId = nil
        appState.selectedJournalId = nil; appState.selectedEmailId = nil
    }

    private func browse() {
        appState.showChannelBrowse = true
        appState.showChannelsHub = false
        appState.selectedThreadId = nil; appState.selectedProjectId = nil
        appState.selectedChannelId = nil; appState.selectedJournalId = nil
    }

    private func load() async {
        async let mineTask = ChannelsService.shared.listChannels()
        async let discoverTask = ChannelsService.shared.discoverChannels()
        let list = (try? await mineTask) ?? []
        let open = (try? await discoverTask) ?? []
        await MainActor.run { channels = list; discover = open; isLoading = false }
    }
}
