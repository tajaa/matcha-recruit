import SwiftUI

struct VerifyWaitView: View {
    let email: String
    @Environment(AppState.self) private var appState
    @State private var vm = AuthViewModel()
    @State private var pastedToken = ""
    @State private var resendCooldownUntil: Date?

    private var resendDisabled: Bool {
        if let until = resendCooldownUntil { return Date() < until }
        return false
    }

    var body: some View {
        ScrollView {
            VStack(spacing: 20) {
                Image(systemName: "envelope.badge.fill")
                    .font(.system(size: 44))
                    .foregroundStyle(.tint)
                    .padding(.top, 40)

                Text("Check your email")
                    .font(.title2.bold())

                Text("We emailed a verification link to \(email). Open it, then come back here.")
                    .multilineTextAlignment(.center)
                    .foregroundStyle(.secondary)
                    .padding(.horizontal)

                ErrorBanner(message: vm.error)

                Button {
                    Task { await vm.retryLoginAfterVerify(appState: appState) }
                } label: {
                    if vm.isLoading {
                        ProgressView().tint(.white)
                    } else {
                        Text("I've verified — sign me in").bold()
                    }
                }
                .frame(maxWidth: .infinity)
                .padding()
                .background(.tint, in: RoundedRectangle(cornerRadius: 10))
                .foregroundStyle(.white)
                .padding(.horizontal)

                Button("Resend email") {
                    resendCooldownUntil = Date().addingTimeInterval(30)
                    Task { await vm.resend(email: email) }
                }
                .disabled(resendDisabled)

                VStack(spacing: 8) {
                    Text("Or paste the verification link/token")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                    TextField("Verification token", text: $pastedToken)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .padding()
                        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 10))
                    Button("Verify") {
                        Task { await vm.verifyPastedToken(pastedToken, appState: appState) }
                    }
                    .disabled(pastedToken.isEmpty)
                }
                .padding(.horizontal)
                .padding(.top, 16)

                Button("Back to login") { appState.phase = .loggedOut }
                    .font(.footnote)
                    .padding(.top, 16)
            }
            .padding(.bottom, 40)
        }
    }
}
