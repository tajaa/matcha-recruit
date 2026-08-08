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
            CreatorTabView()
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

/// Gates on the site list: still loading → spinner, empty → blocking
/// CreateSiteView (no page editor, so this is the only way in), else the
/// real tab shell. `appState.sites`/`activeSite` drive this directly so a
/// site switch or a first-site creation re-renders without any local state.
private struct OwnerRootView: View {
    @Environment(AppState.self) private var appState

    var body: some View {
        Group {
            if appState.sites.isEmpty && appState.sitesLoading {
                ZStack {
                    Color(GummfitTheme.background).ignoresSafeArea()
                    ProgressView()
                }
            } else if appState.sites.isEmpty, let sitesError = appState.sitesError {
                // Load failed before we know whether this account has any
                // sites — show the error + a retry, not the blocking
                // create-site screen (which would misread "couldn't fetch"
                // as "genuinely has none").
                ZStack {
                    Color(GummfitTheme.background).ignoresSafeArea()
                    VStack(spacing: 16) {
                        Text(sitesError).multilineTextAlignment(.center).foregroundStyle(GummfitTheme.textDim)
                        Button("Retry") { Task { await appState.loadSites() } }
                            .buttonStyle(.borderedProminent)
                    }
                    .padding()
                }
            } else if appState.sites.isEmpty {
                NavigationStack { CreateSiteView(isFirstSite: true) }
            } else {
                OwnerTabView()
            }
        }
    }
}
