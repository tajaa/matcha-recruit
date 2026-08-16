import SwiftUI

struct BrandTabView: View {
    @Environment(AppState.self) private var appState

    var body: some View {
        TabView {
            NavigationStack { DashboardView() }
                .tabItem { Label("Dashboard", systemImage: "chart.bar") }

            NavigationStack { FeedbackListView() }
                .tabItem { Label("Feedback", systemImage: "bubble.left.and.text.bubble.right") }

            NavigationStack { BoardManageView(brandId: nil, slug: appState.account?.brand_slug) }
                .tabItem { Label("Locals", systemImage: "person.3") }

            NavigationStack { CampaignsView() }
                .tabItem { Label("Campaigns", systemImage: "ticket.fill") }

            NavigationStack { MessagesListView(scope: .business(brandID: nil)) }
                .tabItem { Label("Comms", systemImage: "message") }

            NavigationStack { BrandMoreView() }
                .tabItem { Label("More", systemImage: "ellipsis.circle") }
        }
    }
}
