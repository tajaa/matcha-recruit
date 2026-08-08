import SwiftUI

/// Shown after signup (verification_required) or a 403-unverified login.
/// Cappe has no deep-link handling (out of scope, see plan), so the only
/// path forward is pasting the emailed token or retrying login after
/// clicking the link on another device.
struct VerifyWaitView: View {
    let email: String
    @Environment(AppState.self) private var appState
    @State private var vm = AuthViewModel()
    @State private var pastedToken = ""
    @State private var resendCooldown = 0
    @State private var cooldownTask: Task<Void, Never>?

    var body: some View {
        ScrollView {
            VStack(spacing: 20) {
                Text("Confirm your email")
                    .font(.title2.bold())

                Text("We sent a confirmation link to \(email). Click it, then come back and tap below.")
                    .font(.subheadline)
                    .foregroundStyle(GummfitTheme.textDim)
                    .multilineTextAlignment(.center)

                ErrorBanner(message: vm.error)

                Button {
                    Task { await vm.retryLoginAfterVerify(appState: appState) }
                } label: {
                    if vm.isLoading {
                        ProgressView()
                    } else {
                        Text("I've confirmed — sign me in").frame(maxWidth: .infinity)
                    }
                }
                .buttonStyle(.borderedProminent)
                .disabled(vm.isLoading)

                TextField("Paste confirmation token", text: $pastedToken)
                    .textFieldStyle(.roundedBorder)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()

                Button("Confirm with pasted token") {
                    Task { await vm.verifyPastedToken(pastedToken, appState: appState) }
                }
                .disabled(pastedToken.isEmpty || vm.isLoading)

                Button(resendCooldown > 0 ? "Resend in \(resendCooldown)s" : "Resend confirmation email") {
                    Task {
                        await vm.resend(email: email)
                        // Only lock the button out if the send actually went
                        // through — a rate-limited (429) or failed resend
                        // must not cost the user a 60s wait with nothing sent.
                        if vm.error == nil { startCooldown() }
                    }
                }
                .disabled(resendCooldown > 0)

                Button("Log out") { appState.didLogout(serverSide: false) }
                    .foregroundStyle(.red)
            }
            .padding(28)
        }
        .onDisappear { cooldownTask?.cancel() }
    }

    private func startCooldown() {
        resendCooldown = 60
        cooldownTask?.cancel()
        cooldownTask = Task { @MainActor in
            while resendCooldown > 0 {
                try? await Task.sleep(for: .seconds(1))
                if Task.isCancelled { return }
                resendCooldown -= 1
            }
        }
    }
}
