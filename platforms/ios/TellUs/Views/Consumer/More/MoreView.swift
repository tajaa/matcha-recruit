import SwiftUI

/// Consumer overflow tab — everything that does not fit the 4 primary tabs
/// (Home/Rewards/Boards/Comms). The admin console stays web-only permanently.
struct MoreView: View {
    @Environment(AppState.self) private var appState
    @State private var showLogoutConfirm = false

    var body: some View {
        List {
            Section {
                NavigationLink {
                    FriendsHubView()
                } label: {
                    HStack {
                        Text("Friends")
                        Spacer()
                        if appState.pendingFriendRequests > 0 {
                            Text("\(appState.pendingFriendRequests)")
                                .font(.interCaption)
                                .foregroundStyle(TU.ink)
                                .padding(.horizontal, 8)
                                .padding(.vertical, 3)
                                .background(TU.ember, in: Capsule())
                        }
                    }
                }
                NavigationLink("My Reviews") { MyReviewsView() }
                NavigationLink("Redemptions") { RedemptionsView() }
                NavigationLink("Leaderboard") { LeaderboardView() }
                NavigationLink("Places") { PlacesView() }
            }
            .listRowBackground(TU.inkRaised)

            Section {
                NavigationLink("Settings") { ConsumerSettingsView() }
            }
            .listRowBackground(TU.inkRaised)

            if !appState.moderatedBrands.isEmpty {
                Section {
                    NavigationLink("Moderate") { ModerateTabView() }
                }
                .listRowBackground(TU.inkRaised)
            }

            Section {
                Button("Sign out", role: .destructive) { showLogoutConfirm = true }
            }
            .listRowBackground(TU.inkRaised)
        }
        .listStyle(.insetGrouped)
        .themedScreen()
        .navigationTitle("More")
        .confirmationDialog(
            "Sign out?", isPresented: $showLogoutConfirm, titleVisibility: .visible
        ) {
            Button("Sign out on all devices", role: .destructive) { appState.didLogout() }
        } message: {
            Text("Beetlejuse has one shared session — this signs you out everywhere.")
        }
    }
}
