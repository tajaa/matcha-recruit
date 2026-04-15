import SwiftUI

struct LoginView: View {
    @Environment(AppState.self) private var appState
    @State private var viewModel = AuthViewModel()
    @State private var animate = false

    var body: some View {
        ZStack {
            // Layered gradient backdrop
            LinearGradient(
                colors: [
                    Color(red: 0.04, green: 0.08, blue: 0.06),
                    Color(red: 0.02, green: 0.04, blue: 0.03),
                    Color.black,
                ],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
            .ignoresSafeArea()

            // Soft ambient glow
            Circle()
                .fill(Color.matcha500.opacity(0.18))
                .frame(width: 520, height: 520)
                .blur(radius: 120)
                .offset(x: -220, y: -180)
                .scaleEffect(animate ? 1.1 : 0.95)
                .animation(.easeInOut(duration: 6).repeatForever(autoreverses: true), value: animate)

            Circle()
                .fill(Color(red: 0.2, green: 0.35, blue: 0.8).opacity(0.15))
                .frame(width: 480, height: 480)
                .blur(radius: 140)
                .offset(x: 240, y: 220)
                .scaleEffect(animate ? 0.95 : 1.08)
                .animation(.easeInOut(duration: 7).repeatForever(autoreverses: true), value: animate)

            VStack(spacing: 28) {
                Spacer(minLength: 0)

                // Brand
                VStack(spacing: 14) {
                    ZStack {
                        RoundedRectangle(cornerRadius: 18)
                            .fill(
                                LinearGradient(
                                    colors: [Color.matcha500, Color.matcha600],
                                    startPoint: .top,
                                    endPoint: .bottom
                                )
                            )
                            .frame(width: 68, height: 68)
                            .shadow(color: Color.matcha500.opacity(0.35), radius: 18, x: 0, y: 8)
                        Image(systemName: "leaf.fill")
                            .font(.system(size: 30, weight: .semibold))
                            .foregroundColor(.white)
                    }

                    VStack(spacing: 4) {
                        Text("Matcha Work")
                            .font(.system(size: 30, weight: .bold))
                            .foregroundColor(.white)
                        Text("Your AI workspace for teams and creators.")
                            .font(.system(size: 13))
                            .foregroundColor(.white.opacity(0.55))
                    }
                }

                // Card
                VStack(spacing: 14) {
                    field(
                        label: "Email",
                        icon: "envelope",
                        placeholder: "you@company.com",
                        text: $viewModel.email,
                        isSecure: false
                    )
                    field(
                        label: "Password",
                        icon: "lock",
                        placeholder: "••••••••",
                        text: $viewModel.password,
                        isSecure: true,
                        onSubmit: { Task { await viewModel.login(appState: appState) } }
                    )

                    if let error = viewModel.errorMessage {
                        HStack(alignment: .top, spacing: 6) {
                            Image(systemName: "exclamationmark.triangle.fill")
                                .font(.system(size: 11))
                                .foregroundColor(.red.opacity(0.8))
                                .padding(.top, 1)
                            Text(errorHint(error))
                                .font(.system(size: 12))
                                .foregroundColor(.red.opacity(0.85))
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }
                        .padding(10)
                        .background(Color.red.opacity(0.08))
                        .overlay(
                            RoundedRectangle(cornerRadius: 8)
                                .stroke(Color.red.opacity(0.25), lineWidth: 1)
                        )
                        .cornerRadius(8)
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
                                HStack(spacing: 6) {
                                    Text("Sign in")
                                    Image(systemName: "arrow.right")
                                        .font(.system(size: 12, weight: .semibold))
                                }
                                .font(.system(size: 14, weight: .semibold))
                            }
                        }
                        .frame(maxWidth: .infinity)
                        .frame(height: 40)
                    }
                    .buttonStyle(.plain)
                    .background(
                        LinearGradient(
                            colors: [Color.matcha500, Color.matcha600],
                            startPoint: .top,
                            endPoint: .bottom
                        )
                    )
                    .foregroundColor(.white)
                    .cornerRadius(10)
                    .shadow(color: Color.matcha500.opacity(0.25), radius: 10, x: 0, y: 4)
                    .disabled(viewModel.isLoading)
                }
                .padding(28)
                .background(
                    RoundedRectangle(cornerRadius: 16)
                        .fill(Color.white.opacity(0.03))
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 16)
                        .stroke(Color.white.opacity(0.08), lineWidth: 1)
                )
                .background(
                    RoundedRectangle(cornerRadius: 16)
                        .fill(.ultraThinMaterial)
                )
                .frame(width: 380)

                Text("v1.0 · \(APIClient.shared.baseURL.replacingOccurrences(of: "https://", with: "").replacingOccurrences(of: "http://", with: ""))")
                    .font(.system(size: 10))
                    .foregroundColor(.white.opacity(0.25))

                Spacer(minLength: 0)
            }
            .padding(.vertical, 32)
        }
        .frame(minWidth: 520, minHeight: 560)
        .onAppear { animate = true }
    }

    @ViewBuilder
    private func field(
        label: String,
        icon: String,
        placeholder: String,
        text: Binding<String>,
        isSecure: Bool,
        onSubmit: (() -> Void)? = nil
    ) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(label)
                .font(.system(size: 12, weight: .medium))
                .foregroundColor(.white.opacity(0.6))
            HStack(spacing: 8) {
                Image(systemName: icon)
                    .font(.system(size: 12))
                    .foregroundColor(.white.opacity(0.4))
                    .frame(width: 14)
                Group {
                    if isSecure {
                        SecureField(placeholder, text: text)
                    } else {
                        TextField(placeholder, text: text)
                    }
                }
                .textFieldStyle(.plain)
                .foregroundColor(.white)
                .font(.system(size: 14))
                .onSubmit { onSubmit?() }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 11)
            .background(Color.black.opacity(0.3))
            .overlay(
                RoundedRectangle(cornerRadius: 10)
                    .stroke(Color.white.opacity(0.1), lineWidth: 1)
            )
            .cornerRadius(10)
        }
    }

    /// Turn technical errors into friendlier hints. In particular, detect
    /// the "server not reachable" case so users know to start the dev
    /// server, not retype their password.
    private func errorHint(_ raw: String) -> String {
        let lowered = raw.lowercased()
        if lowered.contains("could not connect")
            || lowered.contains("connection refused")
            || lowered.contains("offline")
            || lowered.contains("timed out")
            || lowered.contains("not connect to the server") {
            return "Can't reach the server at \(APIClient.shared.baseURL). Start the backend (e.g. `./scripts/dev.sh`) and try again — the app will retry automatically when you focus it."
        }
        return raw
    }
}
