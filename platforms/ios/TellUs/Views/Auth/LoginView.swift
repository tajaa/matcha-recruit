import SwiftUI
import GoogleSignInSwift

struct LoginView: View {
    @Environment(AppState.self) private var appState
    @State private var vm = AuthViewModel()
    @State private var showResetPassword = false
    @FocusState private var focusedField: Field?

    private enum Field { case email, password }

    private var canSubmit: Bool {
        !vm.loginEmail.isEmpty && !vm.loginPassword.isEmpty && !vm.isLoading
    }

    var body: some View {
        ZStack {
            EmberBackground()

            ScrollView {
                VStack(spacing: 0) {
                    header
                        .riseIn(0)
                        .padding(.top, 72)

                    ErrorBanner(message: vm.error)
                        .padding(.top, 24)

                    fields
                        .riseIn(1)
                        .padding(.top, 40)

                    Button {
                        focusedField = nil
                        Task { await vm.login(appState: appState) }
                    } label: {
                        if vm.isLoading {
                            ProgressView().tint(TU.ink)
                        } else {
                            Text("Log in")
                        }
                    }
                    .buttonStyle(EmberButtonStyle(enabled: canSubmit))
                    .disabled(!canSubmit)
                    .riseIn(2)
                    .padding(.top, 16)

                    OrDivider()
                        .riseIn(3)
                        .padding(.top, 20)

                    GoogleSignInButton(scheme: .dark, style: .wide) {
                        focusedField = nil
                        Task { await vm.signInWithGoogle(appState: appState) }
                    }
                    .disabled(vm.isLoading)
                    .riseIn(3)
                    .padding(.top, 12)

                    Button("Have a reset link?") { showResetPassword = true }
                        .font(.custom("Inter-Regular", size: 14))
                        .foregroundStyle(TU.textDim)
                        .riseIn(4)
                        .padding(.top, 20)

                    NavigationLink {
                        SignupView()
                    } label: {
                        Text("Create an account")
                    }
                    .buttonStyle(GhostButtonStyle())
                    .riseIn(5)
                    .padding(.top, 40)
                }
                .padding(.horizontal, 28)
                .padding(.bottom, 48)
            }
            .scrollDismissesKeyboard(.interactively)
        }
        .toolbarBackground(.hidden, for: .navigationBar)
        .sheet(isPresented: $showResetPassword) { ResetPasswordView() }
    }

    private var header: some View {
        VStack(spacing: 16) {
            BrandMark()

            VStack(spacing: 8) {
                Text("Beetlejuse")
                    .font(.custom("Inter-Regular", size: 34).weight(.bold))
                    .tracking(-0.8)
                    .foregroundStyle(.white)

                Text("Say what you think. Leave with points.")
                    .font(.custom("Inter-Regular", size: 15))
                    .foregroundStyle(TU.textDim)
                    .multilineTextAlignment(.center)
            }
        }
    }

    private var fields: some View {
        VStack(spacing: 12) {
            GlassField(isFocused: focusedField == .email) {
                TextField("", text: $vm.loginEmail, prompt: Text("Email").foregroundColor(TU.textDim))
                    .textContentType(.emailAddress)
                    .keyboardType(.emailAddress)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .focused($focusedField, equals: .email)
                    .submitLabel(.next)
                    .onSubmit { focusedField = .password }
            }

            GlassField(isFocused: focusedField == .password) {
                SecureField("", text: $vm.loginPassword, prompt: Text("Password").foregroundColor(TU.textDim))
                    .textContentType(.password)
                    .focused($focusedField, equals: .password)
                    .submitLabel(.go)
                    .onSubmit {
                        guard canSubmit else { return }
                        focusedField = nil
                        Task { await vm.login(appState: appState) }
                    }
            }
        }
    }
}
