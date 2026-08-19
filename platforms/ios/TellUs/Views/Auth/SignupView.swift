import SwiftUI
import GoogleSignInSwift

struct SignupView: View {
    @Environment(AppState.self) private var appState
    @State private var vm: AuthViewModel
    @FocusState private var focusedField: Field?

    private enum Field { case email, password, displayName, brandName, locationCount, city, state }

    init(initialAccountType: AccountType = .consumer) {
        let vm = AuthViewModel()
        vm.accountType = initialAccountType
        _vm = State(initialValue: vm)
    }

    private var canSubmit: Bool {
        !vm.email.isEmpty && vm.password.count >= 8 && !vm.isLoading
    }

    var body: some View {
        ZStack {
            EmberBackground()

            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    Text("Create your account")
                        .font(.custom("Inter-Regular", size: 28).weight(.bold))
                        .tracking(-0.6)
                        .foregroundStyle(.white)
                        .riseIn(0)
                        .padding(.top, 12)

                    accountTypeSwitch
                        .riseIn(1)
                        .padding(.top, 24)

                    ErrorBanner(message: vm.error)
                        .padding(.top, 16)

                    sectionLabel("Account")
                        .padding(.top, 24)
                    accountFields
                        .riseIn(2)
                        .padding(.top, 10)

                    if vm.accountType == .brand {
                        sectionLabel("Brand")
                            .padding(.top, 24)
                        brandFields
                            .padding(.top, 10)
                    } else {
                        sectionLabel("Where you are")
                            .padding(.top, 24)
                        Text("Optional — powers the marketplace and leaderboard.")
                            .font(.custom("Inter-Regular", size: 12))
                            .foregroundStyle(TU.textDim)
                            .padding(.top, 4)
                        consumerFields
                            .padding(.top, 10)
                    }

                    Button {
                        focusedField = nil
                        Task { await vm.signup(appState: appState) }
                    } label: {
                        if vm.isLoading {
                            ProgressView().tint(TU.ink)
                        } else {
                            Text("Create account")
                        }
                    }
                    .buttonStyle(EmberButtonStyle(enabled: canSubmit))
                    .disabled(!canSubmit)
                    .riseIn(3)
                    .padding(.top, 32)

                    if vm.accountType == .consumer {
                        OrDivider()
                            .riseIn(4)
                            .padding(.top, 20)

                        GoogleSignInButton(scheme: .dark, style: .wide) {
                            focusedField = nil
                            Task { await vm.signInWithGoogle(appState: appState) }
                        }
                        .disabled(vm.isLoading)
                        .riseIn(4)
                        .padding(.top, 12)
                    }
                }
                .padding(.horizontal, 24)
                .padding(.bottom, 48)
            }
            .scrollDismissesKeyboard(.interactively)
        }
        .navigationBarTitleDisplayMode(.inline)
        .toolbarBackground(.hidden, for: .navigationBar)
        .animation(.easeOut(duration: 0.2), value: vm.accountType)
    }

    private func sectionLabel(_ text: String) -> some View {
        Text(text.uppercased())
            .font(TU.eyebrow())
            .tracking(1.6)
            .foregroundStyle(TU.textDim)
    }

    // Custom glass segmented pair — .pickerStyle(.segmented) can't carry
    // the amber-on-glass treatment.
    private var accountTypeSwitch: some View {
        HStack(spacing: 4) {
            typeButton(.consumer, label: "Consumer", icon: "person.fill")
            typeButton(.brand, label: "Brand", icon: "storefront.fill")
        }
        .padding(4)
        .background(TU.surface, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .strokeBorder(TU.hairline, lineWidth: 1)
        )
    }

    private func typeButton(_ type: AccountType, label: String, icon: String) -> some View {
        let selected = vm.accountType == type
        return Button {
            vm.accountType = type
        } label: {
            Label(label, systemImage: icon)
                .font(.system(size: 14, weight: selected ? .semibold : .medium))
                .foregroundStyle(selected ? TU.ink : TU.textDim)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 10)
                .background {
                    if selected {
                        RoundedRectangle(cornerRadius: 10, style: .continuous)
                            .fill(TU.ember)
                    }
                }
        }
        .buttonStyle(.plain)
    }

    private var accountFields: some View {
        VStack(spacing: 12) {
            GlassField(isFocused: focusedField == .email) {
                TextField("", text: $vm.email, prompt: Text("Email").foregroundColor(TU.textDim))
                    .textContentType(.emailAddress)
                    .keyboardType(.emailAddress)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .focused($focusedField, equals: .email)
                    .submitLabel(.next)
                    .onSubmit { focusedField = .password }
            }
            GlassField(isFocused: focusedField == .password) {
                SecureField("", text: $vm.password, prompt: Text("Password (min 8 characters)").foregroundColor(TU.textDim))
                    .textContentType(.newPassword)
                    .focused($focusedField, equals: .password)
                    .submitLabel(.next)
                    .onSubmit { focusedField = .displayName }
            }
            GlassField(isFocused: focusedField == .displayName) {
                TextField("", text: $vm.displayName, prompt: Text("Display name (optional)").foregroundColor(TU.textDim))
                    .focused($focusedField, equals: .displayName)
            }
        }
    }

    private var brandFields: some View {
        VStack(spacing: 12) {
            GlassField(isFocused: focusedField == .brandName) {
                TextField("", text: $vm.brandName, prompt: Text("Brand name").foregroundColor(TU.textDim))
                    .focused($focusedField, equals: .brandName)
            }
            GlassField(isFocused: focusedField == .locationCount) {
                TextField("", text: $vm.locationCount, prompt: Text("Number of locations").foregroundColor(TU.textDim))
                    .keyboardType(.numberPad)
                    .focused($focusedField, equals: .locationCount)
            }
        }
    }

    private var consumerFields: some View {
        VStack(spacing: 12) {
            GlassField(isFocused: focusedField == .city) {
                TextField("", text: $vm.city, prompt: Text("City").foregroundColor(TU.textDim))
                    .focused($focusedField, equals: .city)
                    .submitLabel(.next)
                    .onSubmit { focusedField = .state }
            }
            GlassField(isFocused: focusedField == .state) {
                TextField("", text: $vm.state, prompt: Text("State").foregroundColor(TU.textDim))
                    .focused($focusedField, equals: .state)
            }
        }
    }
}
