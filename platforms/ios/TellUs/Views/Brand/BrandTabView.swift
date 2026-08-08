import SwiftUI

struct BrandTabView: View {
    var body: some View {
        TabView {
            NavigationStack { DashboardView() }
                .tabItem { Label("Dashboard", systemImage: "chart.bar") }

            NavigationStack { FeedbackListView() }
                .tabItem { Label("Feedback", systemImage: "bubble.left.and.text.bubble.right") }

            NavigationStack { BoardManageView(brandId: nil) }
                .tabItem { Label("Board", systemImage: "person.3") }

            NavigationStack { NotificationsView() }
                .tabItem { Label("Alerts", systemImage: "bell") }

            NavigationStack { BrandAccountView() }
                .tabItem { Label("Account", systemImage: "person.crop.circle") }
        }
    }
}
