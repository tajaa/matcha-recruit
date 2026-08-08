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
        case .consumer:
            ConsumerTabView()
        case .brand:
            BrandTabView()
        case .brandWall:
            BillingWallView()
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
