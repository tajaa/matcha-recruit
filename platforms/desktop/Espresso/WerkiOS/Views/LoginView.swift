import SwiftUI

struct LoginView: View {
    @Environment(AppState.self) private var appState
    @State private var email = ""
    @State private var password = ""
    @FocusState private var focus: Field?

    private enum Field { case email, password }

    var body: some View {
        ScrollView {
        VStack(spacing: 28) {
            Spacer()
            VStack(spacing: 16) {
                Image("BrandMark").resizable().scaledToFit().frame(width: 104, height: 104)
                    .clipShape(RoundedRectangle(cornerRadius: 26, style: .continuous))
                    .shadow(color: .black.opacity(0.12), radius: 20, y: 10).accessibilityHidden(true)
                Text("Espresso")
                    .font(.largeTitle.weight(.bold)).tracking(-1)
                Text("A little focus. A lot of possibility.")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }

            VStack(alignment: .leading, spacing: 12) {
                Text("WELCOME BACK").font(.caption2.weight(.semibold)).tracking(1.3).foregroundStyle(.secondary)
                TextField("Email", text: $email, prompt: Text("Email").foregroundStyle(EspressoStyle.placeholder))
                    .textContentType(.username)
                    .keyboardType(.emailAddress)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .focused($focus, equals: .email)
                    .submitLabel(.next)
                    .onSubmit { focus = .password }
                    .padding(.vertical, 10)

                Divider()
                SecureField("Password", text: $password, prompt: Text("Password").foregroundStyle(EspressoStyle.placeholder))
                    .textContentType(.password)
                    .focused($focus, equals: .password)
                    .submitLabel(.go)
                    .onSubmit(submit)
                    .padding(.vertical, 10)
            }
            .textFieldStyle(.plain).espressoCard()

            if let err = appState.authError {
                Text(err)
                    .font(.footnote)
                    .foregroundStyle(.red)
                    .multilineTextAlignment(.center)
            }

            Button(action: submit) {
                if appState.isLoggingIn {
                    ProgressView().frame(maxWidth: .infinity)
                } else {
                    Text("Settle in").frame(maxWidth: .infinity)
                }
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
            .disabled(!canSubmit)

            Spacer()
            Spacer()
        }
        .padding(32).padding(.top, 60).frame(maxWidth: 500)
        .frame(maxWidth: .infinity)
        }.espressoBackground()
    }

    private var canSubmit: Bool {
        !email.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && !password.isEmpty && !appState.isLoggingIn
    }

    private func submit() {
        guard canSubmit else { return }
        focus = nil
        Task { await appState.login(email: email.trimmingCharacters(in: .whitespacesAndNewlines), password: password) }
    }
}
