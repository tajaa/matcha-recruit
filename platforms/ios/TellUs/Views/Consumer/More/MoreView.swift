import SwiftUI

/// Consumer overflow tab — everything that does not fit the 4 primary tabs
/// (Home/Rewards/Boards/Comms). The admin console stays web-only permanently.
struct MoreView: View {
    @Environment(AppState.self) private var appState
    @State private var showLogoutConfirm = false

    var body: some View {
        List {
            Section {
                NavigationLink("My Reviews") { MyReviewsView() }
                NavigationLink("Redemptions") { RedemptionsView() }
                NavigationLink("Leaderboard") { LeaderboardView() }
                NavigationLink("Places") { PlacesView() }
            }

            Section {
                NavigationLink("Settings") { ConsumerSettingsView() }
            }

            if !appState.moderatedBrands.isEmpty {
                Section {
                    NavigationLink("Moderate") { ModerateTabView() }
                }
            }

            Section {
                Button("Sign out", role: .destructive) { showLogoutConfirm = true }
            }
        }
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
