import SwiftUI

/// Consumer overflow tab — everything that doesn't fit the 4 primary tabs
/// (Home/Market/Scan/Boards). Rows are added incrementally as their features
/// land natively (Messages, Leaderboard, Settings); Places and the admin
/// console stay web-only permanently.
struct MoreView: View {
    @Environment(AppState.self) private var appState
    @State private var showLogoutConfirm = false

    var body: some View {
        List {
            Section {
                NavigationLink("My Reviews") { MyReviewsView() }
                NavigationLink("Redemptions") { RedemptionsView() }
                NavigationLink("Messages") { MessagesListView() }
                NavigationLink("Leaderboard") { LeaderboardView() }
            }

            Section {
                NavigationLink("Settings") { ConsumerSettingsView() }
            }

            Section {
                Button {
                    SafeURL.open(URL(string: APIClient.shared.webOrigin + "/tellus/places"))
                } label: {
                    HStack {
                        Text("Places")
                        Spacer()
                        Image(systemName: "arrow.up.right.square")
                    }
                }
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
