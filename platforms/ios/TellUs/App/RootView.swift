import SwiftUI

struct RootView: View {
    @Environment(AppState.self) private var appState

    var body: some View {
        Group {
            switch appState.phase {
            case .restoring:
                SplashView()
            case .loggedOut:
                NavigationStack { LoginView() }
            case .verifyPending(let email):
                NavigationStack { VerifyWaitView(email: email) }
            case .consumer:
                ConsumerTabView()
            case .brand:
                BrandTabView()
            case .brandWall:
                BillingWallView()
            }
        }
        .fullScreenCover(item: Binding(
            get: { appState.pendingDeepLink },
            set: { appState.pendingDeepLink = $0 }
        )) { route in
            DeepLinkDestinationView(route: route)
        }
    }
}

/// Presented over the tab trees when a push is tapped. Owns its own
/// `NavigationStack` so the destination can push further (e.g. board feed →
/// post replies) without depending on whichever tab was active.
private struct DeepLinkDestinationView: View {
    let route: DeepLinkRoute
    @Environment(AppState.self) private var appState

    var body: some View {
        NavigationStack {
            switch route {
            case .boardFeed(let slug, let name):
                BoardFeedView(slug: slug, brandName: name)
            case .dmThread(let threadId):
                DmThreadView(vm: DmThreadViewModel(threadId: threadId))
            case .report(let reportId):
                ReportDetailView(id: reportId)
            case .boardManage(let slug):
                BoardManageView(brandId: nil, slug: slug ?? appState.account?.brand_slug)
            }
        }
    }
}

private struct SplashView: View {
    var body: some View {
        ZStack {
            EmberBackground()
            VStack(spacing: 20) {
                BrandMark()
                ProgressView()
                    .tint(TU.textDim)
            }
        }
    }
}
