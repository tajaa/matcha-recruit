import SwiftUI

struct LoginView: View {
    @EnvironmentObject private var authViewModel: AuthViewModel

    @State private var email = ""
    @State private var password = ""
    @FocusState private var focusedField: Field?

    private enum Field {
        case email, password
    }

    var body: some View {
        ZStack {
            // Background
            Color.black.ignoresSafeArea()

            VStack(spacing: 0) {
                Spacer()

                // Logo/Title
                VStack(spacing: 8) {
                    Text("MATCHA")
                        .font(.system(size: 48, weight: .black))
                        .tracking(8)
                        .foregroundColor(.white)

                    Text("TUTOR")
                        .font(.system(size: 14, weight: .bold))
                        .tracking(6)
                        .foregroundColor(.gray)
                }
                .padding(.bottom, 60)

                // Login Form
                VStack(spacing: 20) {
                    // Email Field
                    VStack(alignment: .leading, spacing: 8) {
                        Text("EMAIL")
                            .font(.system(size: 10, weight: .bold))
                            .tracking(2)
                            .foregroundColor(.gray)

                        TextField("", text: $email)
                            .textFieldStyle(DarkTextFieldStyle())
                            .textContentType(.emailAddress)
                            .keyboardType(.emailAddress)
                            .autocapitalization(.none)
                            .autocorrectionDisabled()
                            .focused($focusedField, equals: .email)
                            .submitLabel(.next)
                            .onSubmit {
                                focusedField = .password
                            }
                    }

                    // Password Field
                    VStack(alignment: .leading, spacing: 8) {
                        Text("PASSWORD")
                            .font(.system(size: 10, weight: .bold))
                            .tracking(2)
                            .foregroundColor(.gray)

                        SecureField("", text: $password)
                            .textFieldStyle(DarkTextFieldStyle())
                            .textContentType(.password)
                            .focused($focusedField, equals: .password)
                            .submitLabel(.go)
                            .onSubmit {
                                login()
                            }
                    }

                    // Error Message
                    if let error = authViewModel.errorMessage {
                        HStack {
                            Image(systemName: "exclamationmark.circle.fill")
                                .foregroundColor(.red)
                            Text(error)
                                .font(.system(size: 12))
                                .foregroundColor(.red)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                    }

                    // Login Button
                    Button(action: login) {
                        HStack {
                            if authViewModel.isLoading {
                                ProgressView()
                                    .progressViewStyle(CircularProgressViewStyle(tint: .black))
                                    .scaleEffect(0.8)
                            }
                            Text(authViewModel.isLoading ? "SIGNING IN..." : "SIGN IN")
                                .font(.system(size: 14, weight: .bold))
                                .tracking(2)
                        }
                        .frame(maxWidth: .infinity)
                        .frame(height: 50)
                        .background(isFormValid ? Color.white : Color.gray.opacity(0.3))
                        .foregroundColor(isFormValid ? .black : .gray)
                    }
                    .disabled(!isFormValid || authViewModel.isLoading)
                    .padding(.top, 10)
                }
                .padding(.horizontal, 32)

                Spacer()
                Spacer()
            }
        }
        .onTapGesture {
            focusedField = nil
        }
    }

    private var isFormValid: Bool {
        !email.isEmpty && !password.isEmpty
    }

    private func login() {
        focusedField = nil
        Task {
            await authViewModel.login(email: email, password: password)
        }
    }
}

// MARK: - Custom Text Field Style

struct DarkTextFieldStyle: TextFieldStyle {
    func _body(configuration: TextField<Self._Label>) -> some View {
        configuration
            .padding(.horizontal, 16)
            .padding(.vertical, 14)
            .background(Color(white: 0.1))
            .foregroundColor(.white)
            .font(.system(size: 16))
            .overlay(
                RoundedRectangle(cornerRadius: 0)
                    .stroke(Color(white: 0.2), lineWidth: 1)
            )
    }
}

#Preview {
    LoginView()
        .environmentObject(AuthViewModel())
}
