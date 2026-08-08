import SwiftUI

struct SignupView: View {
    @Environment(AppState.self) private var appState
    @State private var vm = AuthViewModel()
    @FocusState private var focusedField: Field?

    private enum Field { case name, email, password }

    private var canSubmit: Bool {
        !vm.email.isEmpty && vm.password.count >= 8 && !vm.isLoading
    }

    var body: some View {
        ScrollView {
            VStack(spacing: 0) {
                Text("Create your account")
                    .font(.title2.bold())
                    .padding(.top, 24)

                ErrorBanner(message: vm.error)
                    .padding(.top, 16)

                Picker("Account type", selection: $vm.accountType) {
                    Text("Business").tag(AccountType.business)
                    Text("Personal").tag(AccountType.personal)
                    Text("Creator").tag(AccountType.creator)
                }
                .pickerStyle(.segmented)
                .padding(.top, 24)

                VStack(spacing: 12) {
                    TextField("Name (optional)", text: $vm.displayName)
                        .textContentType(.name)
                        .focused($focusedField, equals: .name)
                        .textFieldStyle(.roundedBorder)

                    TextField("Email", text: $vm.email)
                        .textContentType(.emailAddress)
                        .keyboardType(.emailAddress)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .focused($focusedField, equals: .email)
                        .textFieldStyle(.roundedBorder)

                    SecureField("Password (min 8 characters)", text: $vm.password)
                        .textContentType(.newPassword)
                        .focused($focusedField, equals: .password)
                        .textFieldStyle(.roundedBorder)
                }
                .padding(.top, 20)

                Button {
                    focusedField = nil
                    Task { await vm.signup(appState: appState) }
                } label: {
                    if vm.isLoading {
                        ProgressView()
                    } else {
                        Text("Sign up").frame(maxWidth: .infinity)
                    }
                }
                .buttonStyle(.borderedProminent)
                .disabled(!canSubmit)
                .padding(.top, 24)
            }
            .padding(.horizontal, 28)
            .padding(.bottom, 48)
        }
        .scrollDismissesKeyboard(.interactively)
    }
}
