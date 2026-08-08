import SwiftUI

struct BillingWallView: View {
    @Environment(AppState.self) private var appState
    @State private var isRefreshing = false
    @State private var showLogoutConfirm = false

    var body: some View {
        VStack(spacing: 20) {
            Spacer()
            Image(systemName: "creditcard.trianglebadge.exclamationmark")
                .font(.system(size: 48))
                .foregroundStyle(.orange)
            Text("Your Tell-Us plan isn't active")
                .font(.title2.bold())
                .multilineTextAlignment(.center)
            Text("Manage billing on the web to reactivate your brand dashboard.")
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 32)

            Button {
                SafeURL.open(URL(string: APIClient.shared.webOrigin + "/tellus/brand/billing"))
            } label: {
                Text("Manage billing on web").bold()
            }
            .frame(maxWidth: .infinity)
            .padding()
            .background(.tint, in: RoundedRectangle(cornerRadius: 10))
            .foregroundStyle(.white)
            .padding(.horizontal, 32)

            Button {
                Task {
                    isRefreshing = true
                    await appState.refreshWall()
                    isRefreshing = false
                }
            } label: {
                if isRefreshing { ProgressView() } else { Text("Refresh") }
            }

            Spacer()

            Button("Sign out", role: .destructive) { showLogoutConfirm = true }
                .padding(.bottom, 24)
        }
        .confirmationDialog(
            "Sign out?",
            isPresented: $showLogoutConfirm,
            titleVisibility: .visible
        ) {
            Button("Sign out on all devices", role: .destructive) { appState.didLogout() }
        } message: {
            Text("Tell-Us has one shared session — this signs you out everywhere.")
        }
    }
}
