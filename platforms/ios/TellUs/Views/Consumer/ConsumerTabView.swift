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

            NavigationStack { CommsHubView() }
                .tabItem { Label("Comms", systemImage: "message") }

            NavigationStack { MoreView() }
                .tabItem { Label("More", systemImage: "ellipsis.circle") }
        }
    }
}
