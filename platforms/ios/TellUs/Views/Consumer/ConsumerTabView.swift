import SwiftUI

struct ConsumerTabView: View {
    @Environment(AppState.self) private var appState

    var body: some View {
        @Bindable var appState = appState
        TabView {
            NavigationStack { RewardsHomeView() }
                .tabItem { Label("Home", systemImage: "sparkles") }

            NavigationStack { MarketplaceHomeView() }
                .tabItem { Label("Rewards", systemImage: "gift") }

            NavigationStack { BoardsListView() }
                .tabItem { Label("Boards", systemImage: "person.3") }

            NavigationStack { CommsHubView() }
                .tabItem { Label("Comms", systemImage: "message") }

            NavigationStack { MoreView() }
                .tabItem { Label("More", systemImage: "ellipsis.circle") }
        }
    }
}
