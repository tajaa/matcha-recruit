import SwiftUI

struct BrandAccountView: View {
    @Environment(AppState.self) private var appState
    @State private var showLogoutConfirm = false

    private var webBase: String { APIClient.shared.webOrigin + "/tellus/brand" }

    var body: some View {
        Form {
            if let account = appState.account {
                Section {
                    Text(account.email)
                    if let slug = account.brand_slug {
                        Text("tellus/b/\(slug)").font(.caption).foregroundStyle(.secondary)
                    }
                    LabeledContent("Plan", value: account.plan_status?.rawValue.capitalized ?? "—")
                }
            }

            Section("Manage on web") {
                webLink("Billing", "/billing")
                webLink("Stores & QR codes", "/stores")
                webLink("Reward listings", "/listings")
                webLink("Settings & prompts", "/settings")
                webLink("Messages", "/messages")
            }

            Section {
                Button("Sign out", role: .destructive) { showLogoutConfirm = true }
            }
        }
        .navigationTitle("Account")
        .confirmationDialog(
            "Sign out?", isPresented: $showLogoutConfirm, titleVisibility: .visible
        ) {
            Button("Sign out on all devices", role: .destructive) { appState.didLogout() }
        } message: {
            Text("Tell-Us has one shared session — this signs you out everywhere.")
        }
    }

    private func webLink(_ label: String, _ path: String) -> some View {
        Button {
            SafeURL.open(URL(string: webBase + path))
        } label: {
            HStack {
                Text(label)
                Spacer()
                Image(systemName: "arrow.up.right.square")
            }
        }
    }
}
