import SwiftUI

/// Authenticated root tab bar: real-time channels + direct messages. A tapped
/// push switches to the relevant tab; the list views consume the pending id.
struct MainTabView: View {
    @Environment(AppState.self) private var appState
    @State private var tab = 0

    var body: some View {
        TabView(selection: $tab) {
            ChannelListView()
                .tag(0)
                .tabItem { Label("Channels", systemImage: "number") }
            InboxListView()
                .tag(1)
                .tabItem { Label("Messages", systemImage: "bubble.left.and.bubble.right") }
        }
        .onChange(of: appState.pendingChannelId) { _, value in
            if value != nil { tab = 0 }
        }
        .onChange(of: appState.pendingConversationId) { _, value in
            if value != nil { tab = 1 }
        }
    }
}
