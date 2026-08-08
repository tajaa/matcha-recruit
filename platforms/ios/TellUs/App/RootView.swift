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
        VStack(spacing: 12) {
            Image(systemName: "bubble.left.and.bubble.right.fill")
                .font(.system(size: 44))
                .foregroundStyle(.tint)
            ProgressView()
        }
    }
}
