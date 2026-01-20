import SwiftUI

@main
struct MatchaTutorApp: App {
    @StateObject private var authViewModel = AuthViewModel()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(authViewModel)
                .preferredColorScheme(.dark)
                .task {
                    await authViewModel.checkAuthStatus()
                }
        }
    }
}
