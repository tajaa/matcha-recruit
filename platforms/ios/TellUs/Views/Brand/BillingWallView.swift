import SwiftUI

struct BillingWallView: View {
    @Environment(AppState.self) private var appState
    @State private var isRefreshing = false
    @State private var showLogoutConfirm = false
    @State private var showBilling = false
    @State private var showComms = false

    var body: some View {
        VStack(spacing: 20) {
            Spacer()
            Image(systemName: "creditcard.trianglebadge.exclamationmark")
                .font(.custom("Inter-Regular", size: 48))
                .foregroundStyle(.orange)
            Text("Your Beetlejuse plan isn't active")
                .font(.interTitle2.bold())
                .multilineTextAlignment(.center)
            Text("Manage billing to reactivate your brand dashboard.")
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 32)

            Button {
                showBilling = true
            } label: {
                Text("Manage billing").bold()
            }
            .frame(maxWidth: .infinity)
            .padding()
            .background(.tint, in: RoundedRectangle(cornerRadius: 10))
            .foregroundStyle(.white)
            .padding(.horizontal, 32)

            Button {
                showComms = true
            } label: {
                Label("Open Comms inbox", systemImage: "message")
            }

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
            Text("Beetlejuse has one shared session — this signs you out everywhere.")
        }
        .sheet(isPresented: $showBilling) { NavigationStack { BillingView() } }
        .sheet(isPresented: $showComms) { NavigationStack { MessagesListView(scope: .business(brandID: nil)) } }
    }
}
