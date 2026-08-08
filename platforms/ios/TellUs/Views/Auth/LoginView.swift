import SwiftUI

struct LoginView: View {
    @Environment(AppState.self) private var appState
    @State private var vm = AuthViewModel()
    @State private var showResetPassword = false
    @FocusState private var focusedField: Field?

    private enum Field { case email, password }

    var body: some View {
        ScrollView {
            VStack(spacing: 20) {
                Image(systemName: "bubble.left.and.bubble.right.fill")
                    .font(.system(size: 48))
                    .foregroundStyle(.tint)
                    .padding(.top, 40)

                Text("Tell-Us")
                    .font(.largeTitle.bold())

                ErrorBanner(message: vm.error)

                VStack(spacing: 12) {
                    TextField("Email", text: $vm.loginEmail)
                        .textContentType(.emailAddress)
                        .keyboardType(.emailAddress)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .focused($focusedField, equals: .email)
                        .submitLabel(.next)
                        .onSubmit { focusedField = .password }
                        .padding()
                        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 10))

                    SecureField("Password", text: $vm.loginPassword)
                        .textContentType(.password)
                        .focused($focusedField, equals: .password)
                        .submitLabel(.go)
                        .onSubmit { Task { await vm.login(appState: appState) } }
                        .padding()
                        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 10))
                }
                .padding(.horizontal)

                Button {
                    Task { await vm.login(appState: appState) }
                } label: {
                    if vm.isLoading {
                        ProgressView().tint(.white)
                    } else {
                        Text("Log In").bold()
                    }
                }
                .frame(maxWidth: .infinity)
                .padding()
                .background(.tint, in: RoundedRectangle(cornerRadius: 10))
                .foregroundStyle(.white)
                .disabled(vm.loginEmail.isEmpty || vm.loginPassword.isEmpty || vm.isLoading)
                .padding(.horizontal)

                NavigationLink("Create an account") { SignupView() }
                    .padding(.top, 8)

                Button("Have a reset link?") { showResetPassword = true }
                    .font(.footnote)
            }
            .padding(.bottom, 40)
        }
        .scrollDismissesKeyboard(.interactively)
        .sheet(isPresented: $showResetPassword) { ResetPasswordView() }
    }
}
