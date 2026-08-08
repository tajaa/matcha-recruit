import SwiftUI

/// Owner tab shell (plan §6). Home/Catalog/Sales/Inbox are real (Phases
/// 2-5); the rest of §6's "More" list (Subscribers/Campaigns/Forms/Blog/
/// Collabs) arrives with Phase 6/7. Reads `appState.activeSite` directly
/// (not a captured `let`) so a site switch — which mutates AppState, not
/// this view's identity — rebuilds every tab with the new site.
struct OwnerTabView: View {
    @Environment(AppState.self) private var appState
    @Environment(\.scenePhase) private var scenePhase

    var body: some View {
        TabView {
            NavigationStack {
                if let site = appState.activeSite {
                    HomeView(site: site).id(site.id)
                }
            }
            .tabItem { Label("Home", systemImage: "house") }

            Group {
                if let site = appState.activeSite {
                    CatalogRootView(site: site).id(site.id)
                }
            }
            .tabItem { Label("Catalog", systemImage: "square.grid.2x2") }

            Group {
                if let site = appState.activeSite {
                    SalesRootView(site: site).id(site.id)
                }
            }
            .tabItem { Label("Sales", systemImage: "bag") }

            Group {
                if let site = appState.activeSite {
                    InboxRootView(site: site).id(site.id)
                }
            }
            .tabItem { Label("Inbox", systemImage: "envelope") }
            .badge(appState.unreadCount)

            moreTab
                .tabItem { Label("More", systemImage: "ellipsis") }
        }
        // The poll itself lives on AppState (plan §5) so it survives tab
        // switches and pauses while backgrounded — scenePhase is only
        // readable from a View, so it's threaded through here.
        .onAppear { appState.restartUnreadPoll() }
        .onChange(of: scenePhase) { _, newPhase in
            appState.setScenePhaseActive(newPhase == .active)
        }
    }

    /// Sign-out plus the CRM/Venue screens that don't have their own tab.
    /// Locations & Staff only appears for multi-location sites.
    private var moreTab: some View {
        NavigationStack {
            List {
                if let site = appState.activeSite {
                    Section {
                        NavigationLink("Clients") { ClientsView(site: site) }
                        NavigationLink("Reviews") { ReviewsView(site: site) }
                        if site.is_multi_location {
                            NavigationLink("Locations & Staff") { LocationsStaffView(site: site) }
                        }
                    }
                }
                Section {
                    Button("Sign out", role: .destructive) { appState.didLogout() }
                }
            }
            .navigationTitle("More")
        }
    }
}
