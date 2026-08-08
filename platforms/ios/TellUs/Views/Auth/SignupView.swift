import SwiftUI

struct SignupView: View {
    @Environment(AppState.self) private var appState
    @State private var vm = AuthViewModel()

    var body: some View {
        Form {
            Section {
                Picker("Account type", selection: $vm.accountType) {
                    Text("Consumer").tag(AccountType.consumer)
                    Text("Brand").tag(AccountType.brand)
                }
                .pickerStyle(.segmented)
            }

            Section("Account") {
                TextField("Email", text: $vm.email)
                    .textContentType(.emailAddress)
                    .keyboardType(.emailAddress)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                SecureField("Password (min 8 characters)", text: $vm.password)
                    .textContentType(.newPassword)
                TextField("Display name (optional)", text: $vm.displayName)
            }

            if vm.accountType == .brand {
                Section("Brand") {
                    TextField("Brand name", text: $vm.brandName)
                    TextField("Number of locations", text: $vm.locationCount)
                        .keyboardType(.numberPad)
                }
            } else {
                Section("Location (optional — powers the marketplace & leaderboard)") {
                    TextField("City", text: $vm.city)
                    TextField("State", text: $vm.state)
                }
            }

            if let error = vm.error {
                Section { Text(error).foregroundStyle(.red).font(.footnote) }
            }

            Section {
                Button {
                    Task { await vm.signup(appState: appState) }
                } label: {
                    if vm.isLoading {
                        ProgressView()
                    } else {
                        Text("Create account").bold()
                    }
                }
                .disabled(vm.email.isEmpty || vm.password.count < 8 || vm.isLoading)
            }
        }
        .navigationTitle("Sign Up")
    }
}
