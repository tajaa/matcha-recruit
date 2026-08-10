import SwiftUI

/// Creator tab shell (plan §6). All content is Phase 7 (creator profile /
/// deals / earnings) — this just gives creator accounts a real destination
/// (and a way to sign out) instead of the Phase 0 placeholder root.
struct CreatorTabView: View {
    @Environment(AppState.self) private var appState

    var body: some View {
        TabView {
            CreatorProfileView()
                .tabItem { Label("Profile", systemImage: "person.crop.circle") }

            CreatorDealsView()
                .tabItem { Label("Deals", systemImage: "star.bubble") }

            EarningsView()
                .tabItem { Label("Earnings", systemImage: "dollarsign.circle") }

            accountTab
                .tabItem { Label("Account", systemImage: "gearshape") }
        }
    }

    private var accountTab: some View {
        NavigationStack {
            List {
                Section {
                    Text(appState.account?.email ?? "")
                        .foregroundStyle(GummfitTheme.textDim)
                }
                Section {
                    Button("Sign out", role: .destructive) { appState.didLogout() }
                }
            }
            .navigationTitle("Account")
        }
    }
}
