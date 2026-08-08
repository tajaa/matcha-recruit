import SwiftUI

struct ConsumerTabView: View {
    @Environment(AppState.self) private var appState

    var body: some View {
        @Bindable var appState = appState
        TabView {
            NavigationStack { RewardsHomeView() }
                .tabItem { Label("Home", systemImage: "sparkles") }

            NavigationStack { MarketplaceHomeView() }
                .tabItem { Label("Market", systemImage: "gift") }

            NavigationStack { ScanView() }
                .tabItem { Label("Scan", systemImage: "qrcode.viewfinder") }

            NavigationStack { BoardsListView() }
                .tabItem { Label("Boards", systemImage: "person.3") }

            NavigationStack { MyReviewsView() }
                .tabItem { Label("Reviews", systemImage: "star.bubble") }

            if !appState.moderatedBrands.isEmpty {
                NavigationStack { ModerateTabView() }
                    .tabItem { Label("Moderate", systemImage: "checkmark.shield") }
            }
        }
    }
}
