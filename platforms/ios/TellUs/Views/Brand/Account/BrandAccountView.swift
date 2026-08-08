import SwiftUI

struct BrandAccountView: View {
    @Environment(AppState.self) private var appState
    @State private var showLogoutConfirm = false

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
}
