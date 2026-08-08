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
            if !appState.sitesLoaded && appState.sitesError == nil {
                // Covers "task hasn't run yet" and "in flight" — gating on
                // `sitesLoading` alone flips true→false in the wrong order
                // (route() sets phase synchronously, sitesLoading later) and
                // would fall through to the blocking create screen.
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
                        Button("Sign out", role: .destructive) { appState.didLogout() }
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
