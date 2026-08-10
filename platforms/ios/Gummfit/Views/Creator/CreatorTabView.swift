import SwiftUI

enum CreatorTab: Hashable {
    case home
    case profile
    case deals
    case earnings
    case account
}

/// Creator tab shell (plan §6). All content is Phase 7 (creator profile /
/// deals / earnings) — this just gives creator accounts a real destination
/// (and a way to sign out) instead of the Phase 0 placeholder root.
struct CreatorTabView: View {
    @Environment(AppState.self) private var appState
    @State private var selectedTab: CreatorTab = .home

    var body: some View {
        TabView(selection: $selectedTab) {
            CreatorDashboardView(onSelect: { selectedTab = $0 })
                .tabItem { Label("Home", systemImage: "house") }
                .tag(CreatorTab.home)

            CreatorProfileView()
                .tabItem { Label("Profile", systemImage: "person.crop.circle") }
                .tag(CreatorTab.profile)

            CreatorDealsView()
                .tabItem { Label("Deals", systemImage: "star.bubble") }
                .tag(CreatorTab.deals)

            EarningsView()
                .tabItem { Label("Earnings", systemImage: "dollarsign.circle") }
                .tag(CreatorTab.earnings)

            accountTab
                .tabItem { Label("Account", systemImage: "gearshape") }
                .tag(CreatorTab.account)
        }
        .tint(GummfitTheme.accent)
        .preferredColorScheme(.dark)
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
                Section("Payouts") {
                    Link("Set up payouts on web", destination: URL(string: "\(APIClient.shared.webOrigin)/creator/payouts")!)
                }
            }
            .navigationTitle("Account")
            .listStyle(.insetGrouped)
            .gummfitListBackground()
            .gummfitScreenChrome()
        }
    }
}
