import SwiftUI

struct LoginView: View {
    @Environment(AppState.self) private var appState
    @State private var viewModel = AuthViewModel()

    var body: some View {
        ZStack {
            Color.appBackground
                .ignoresSafeArea()

            VStack(spacing: 0) {
                // Logo/Title
                VStack(spacing: 8) {
                    Circle()
                        .fill(Color.matcha500)
                        .frame(width: 48, height: 48)
                        .overlay(
                            Text("M")
                                .font(.system(size: 24, weight: .bold))
                                .foregroundColor(.white)
                        )

                    Text("Matcha")
                        .font(.system(size: 28, weight: .bold))
                        .foregroundColor(.white)

                    Text("Sign in to your workspace")
                        .font(.system(size: 14))
                        .foregroundColor(.secondary)
                }
                .padding(.bottom, 32)

                // Card
                VStack(spacing: 16) {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("Email")
                            .font(.system(size: 13, weight: .medium))
                            .foregroundColor(.secondary)
                        TextField("you@company.com", text: $viewModel.email)
                            .textFieldStyle(.plain)
                            .padding(10)
                            .background(Color.zinc950)
                            .cornerRadius(8)
                            .overlay(
                                RoundedRectangle(cornerRadius: 8)
                                    .stroke(Color.borderColor, lineWidth: 1)
                            )
                            .foregroundColor(.white)
                            .font(.system(size: 14))
                    }

                    VStack(alignment: .leading, spacing: 6) {
                        Text("Password")
                            .font(.system(size: 13, weight: .medium))
                            .foregroundColor(.secondary)
                        SecureField("••••••••", text: $viewModel.password)
                            .textFieldStyle(.plain)
                            .padding(10)
                            .background(Color.zinc950)
                            .cornerRadius(8)
                            .overlay(
                                RoundedRectangle(cornerRadius: 8)
                                    .stroke(Color.borderColor, lineWidth: 1)
                            )
                            .foregroundColor(.white)
                            .font(.system(size: 14))
                            .onSubmit {
                                Task { await viewModel.login(appState: appState) }
                            }
                    }

                    if let error = viewModel.errorMessage {
                        Text(error)
                            .font(.system(size: 13))
                            .foregroundColor(.red)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }

                    Button {
                        Task { await viewModel.login(appState: appState) }
                    } label: {
                        Group {
                            if viewModel.isLoading {
                                ProgressView()
                                    .progressViewStyle(.circular)
                                    .controlSize(.small)
                                    .tint(.white)
                            } else {
                                Text("Sign in")
                                    .font(.system(size: 14, weight: .semibold))
                            }
                        }
                        .frame(maxWidth: .infinity)
                        .frame(height: 36)
                    }
                    .buttonStyle(.plain)
                    .background(Color.matcha600)
                    .foregroundColor(.white)
                    .cornerRadius(8)
                    .disabled(viewModel.isLoading)
                }
                .padding(24)
                .background(Color.zinc900)
                .cornerRadius(12)
                .overlay(
                    RoundedRectangle(cornerRadius: 12)
                        .stroke(Color.borderColor, lineWidth: 1)
                )
                .frame(width: 360)
            }
        }
        .frame(minWidth: 500, minHeight: 400)
    }
}
