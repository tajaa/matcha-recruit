import SwiftUI

/// Owner tab shell (plan §6). Home is real (Phase 2); Sales/Inbox/Catalog/
/// More are placeholders until their owning phases (4/5/3/6). Reads
/// `appState.activeSite` directly (not a captured `let`) so a site switch —
/// which mutates AppState, not this view's identity — rebuilds Home with
/// the new site.
struct OwnerTabView: View {
    @Environment(AppState.self) private var appState

    var body: some View {
        TabView {
            NavigationStack {
                if let site = appState.activeSite {
                    HomeView(site: site).id(site.id)
                }
            }
            .tabItem { Label("Home", systemImage: "house") }

            PlaceholderTab(title: "Sales")
                .tabItem { Label("Sales", systemImage: "bag") }

            PlaceholderTab(title: "Inbox")
                .tabItem { Label("Inbox", systemImage: "envelope") }

            PlaceholderTab(title: "Catalog")
                .tabItem { Label("Catalog", systemImage: "square.grid.2x2") }

            moreTab
                .tabItem { Label("More", systemImage: "ellipsis") }
        }
    }

    /// Real content (sign-out) lands here now; the rest of §6's "More" list
    /// (Clients/Reviews/Subscribers/Campaigns/Forms/Blog/Locations/Collabs)
    /// arrives with its owning phase.
    private var moreTab: some View {
        NavigationStack {
            List {
                Section {
                    Button("Sign out", role: .destructive) { appState.didLogout() }
                }
            }
            .navigationTitle("More")
        }
    }
}
