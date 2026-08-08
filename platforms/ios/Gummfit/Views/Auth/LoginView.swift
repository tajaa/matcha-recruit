import SwiftUI

struct LoginView: View {
    @Environment(AppState.self) private var appState
    @State private var vm = AuthViewModel()
    @FocusState private var focusedField: Field?

    private enum Field { case email, password }

    private var canSubmit: Bool {
        !vm.loginEmail.isEmpty && !vm.loginPassword.isEmpty && !vm.isLoading
    }

    var body: some View {
        ScrollView {
            VStack(spacing: 0) {
                header.padding(.top, 72)

                ErrorBanner(message: vm.error)
                    .padding(.top, 24)

                fields.padding(.top, 40)

                Button {
                    focusedField = nil
                    Task { await vm.login(appState: appState) }
                } label: {
                    if vm.isLoading {
                        ProgressView()
                    } else {
                        Text("Log in").frame(maxWidth: .infinity)
                    }
                }
                .buttonStyle(.borderedProminent)
                .disabled(!canSubmit)
                .padding(.top, 16)

                NavigationLink {
                    SignupView()
                } label: {
                    Text("Create an account")
                }
                .padding(.top, 24)
            }
            .padding(.horizontal, 28)
            .padding(.bottom, 48)
        }
        .scrollDismissesKeyboard(.interactively)
    }

    private var header: some View {
        VStack(spacing: 8) {
            Text("Gummfit")
                .font(.system(size: 34, weight: .bold))
                .tracking(-0.8)

            Text("Run your storefront from your phone.")
                .font(.system(size: 15))
                .foregroundStyle(GummfitTheme.textDim)
                .multilineTextAlignment(.center)
        }
    }

    private var fields: some View {
        VStack(spacing: 12) {
            TextField("Email", text: $vm.loginEmail)
                .textContentType(.emailAddress)
                .keyboardType(.emailAddress)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .focused($focusedField, equals: .email)
                .submitLabel(.next)
                .onSubmit { focusedField = .password }
                .textFieldStyle(.roundedBorder)

            SecureField("Password", text: $vm.loginPassword)
                .textContentType(.password)
                .focused($focusedField, equals: .password)
                .submitLabel(.go)
                .onSubmit {
                    guard canSubmit else { return }
                    focusedField = nil
                    Task { await vm.login(appState: appState) }
                }
                .textFieldStyle(.roundedBorder)
        }
    }
}
