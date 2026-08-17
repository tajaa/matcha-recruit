import SwiftUI

struct FriendProfileView: View {
    @Environment(\.dismiss) private var dismiss
    let accountId: String
    @State private var profile: FriendProfile?
    @State private var error: String?
    @State private var isBusy = false
    @State private var showUnfriendConfirm = false
    @State private var showBlockConfirm = false
    @State private var showReport = false

    var body: some View {
        List {
            if let profile {
                Section {
                    HStack(spacing: 14) {
                        Avatar(profile, size: .header)
                        VStack(alignment: .leading, spacing: 4) {
                            Text(profile.display_name).font(.interTitle3)
                            if let handle = profile.handle { Text("@\(handle)").font(.interCaption).foregroundStyle(TU.textDim) }
                            Text(profile.level.map { "Level \($0) · " } ?? "")
                                .font(.interCaption).foregroundStyle(TU.textDim)
                            Text("\(profile.friend_count) friends").font(.interCaption).foregroundStyle(TU.textDim)
                        }
                    }
                    actionButton(profile)
                }
                if let reviews = profile.reviews { Section("Reviews") { ForEach(reviews) { review in Text(review.title ?? review.brand_name) } } }
                if let places = profile.followed_places { Section("Places") { ForEach(places) { Text($0.name) } } }
                if let badges = profile.badges {
                    Section { BadgesGrid(badges: badges.map {
                        BadgeItem(key: $0.key, name: $0.name, description: $0.description,
                                  icon: $0.icon, earned: true, awarded_at: $0.awarded_at)
                    }) }
                }
                if let boards = profile.boards { Section("Boards") { ForEach(boards) { Text($0.brand_name) } } }
            } else if error == nil { ProgressView() }
        }
        .listStyle(.insetGrouped)
        .themedScreen()
        .navigationTitle(profile?.display_name ?? "Profile")
        .task {
            await load()
        }
        .refreshable { await load() }
        .toolbar {
            if profile?.is_you == false {
                Menu {
                    if profile?.is_friend == true {
                        Button("Unfriend", role: .destructive) { showUnfriendConfirm = true }
                    }
                    Button("Block", role: .destructive) { showBlockConfirm = true }
                    Button("Report") { showReport = true }
                } label: { Image(systemName: "ellipsis") }
            }
        }
        .confirmationDialog("Unfriend \(profile?.display_name ?? "this person")?", isPresented: $showUnfriendConfirm, titleVisibility: .visible) {
            Button("Unfriend", role: .destructive) { run { try await FriendsService.shared.removeFriend(accountId: accountId); await load() } }
        }
        .confirmationDialog("Block \(profile?.display_name ?? "this person")?", isPresented: $showBlockConfirm, titleVisibility: .visible) {
            Button("Block", role: .destructive) { run { try await FriendsService.shared.block(accountId: accountId); dismiss() } }
        } message: {
            Text("Blocking removes the friendship and cancels pending requests.")
        }
        .sheet(isPresented: $showReport) { FriendReportSheet(accountId: accountId) }
        .overlay(alignment: .top) { ErrorBanner(message: error).padding(.top, 8) }
    }

    @ViewBuilder
    private func actionButton(_ profile: FriendProfile) -> some View {
        switch profile.status {
        case .none:
            Button("Add Friend") { run { _ = try await FriendsService.shared.request(accountId: accountId); await load() } }
                .buttonStyle(EmberButtonStyle())
        case .pending_in:
            Button("Accept Request") {
                run { _ = try await FriendsService.shared.accept(requestId: profile.pending_request_id ?? ""); await load() }
            }
            .buttonStyle(EmberButtonStyle())
        case .pending_out:
            Button("Cancel Request", role: .destructive) {
                run { try await FriendsService.shared.cancel(requestId: profile.pending_request_id ?? ""); await load() }
            }
        case .friends:
            Text("Friends").foregroundStyle(TU.textDim)
        case .blocked, .blocked_by, .unknown:
            EmptyView()
        }
    }

    private func load() async {
        do { profile = try await FriendsService.shared.profile(accountId: accountId) }
        catch { if !error.isCancellation { self.error = error.localizedDescription } }
    }

    private func run(_ operation: @escaping () async throws -> Void) {
        guard !isBusy else { return }
        isBusy = true
        Task {
            defer { isBusy = false }
            do { try await operation() }
            catch { if !error.isCancellation { self.error = error.localizedDescription } }
        }
    }
}
