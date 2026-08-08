import SwiftUI

struct RootView: View {
    @Environment(AppState.self) private var appState

    var body: some View {
        switch appState.phase {
        case .restoring:
            SplashView()
        case .loggedOut:
            NavigationStack { LoginView() }
        case .verifyPending(let email):
            NavigationStack { VerifyWaitView(email: email) }
        case .owner:
            OwnerRootView()
        case .creator:
            CreatorRootView()
        }
    }
}

private struct SplashView: View {
    var body: some View {
        ZStack {
            Color(GummfitTheme.background).ignoresSafeArea()
            ProgressView()
        }
    }
}

/// Placeholder — replaced by the real site-switcher TabView in Phase 1/2.
private struct OwnerRootView: View {
    @Environment(AppState.self) private var appState

    var body: some View {
        NavigationStack {
            VStack(spacing: 16) {
                Text("Signed in as \(appState.account?.email ?? "")")
                Button("Sign out") { appState.didLogout() }
            }
            .navigationTitle("Gummfit")
        }
    }
}

/// Placeholder — replaced by the real CreatorTabView in Phase 1/7.
private struct CreatorRootView: View {
    @Environment(AppState.self) private var appState

    var body: some View {
        NavigationStack {
            VStack(spacing: 16) {
                Text("Signed in as \(appState.account?.email ?? "")")
                Button("Sign out") { appState.didLogout() }
            }
            .navigationTitle("Gummfit Creator")
        }
    }
}
