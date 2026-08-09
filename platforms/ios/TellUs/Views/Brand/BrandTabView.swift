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
                .tabItem { Label("Board", systemImage: "person.3") }

            NavigationStack { BrandScanView() }
                .tabItem { Label("Redeem", systemImage: "qrcode.viewfinder") }

            NavigationStack { MessagesListView() }
                .tabItem { Label("Messages", systemImage: "message") }

            NavigationStack { BrandMoreView() }
                .tabItem { Label("More", systemImage: "ellipsis.circle") }
        }
    }
}
