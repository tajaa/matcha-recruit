import SwiftUI

struct LoginView: View {
    @Environment(AppState.self) private var appState
    @State private var viewModel = AuthViewModel()
    @State private var animate = false

    var body: some View {
        ZStack {
            // Light-gray gradient backdrop — the platinum brand identity.
            LinearGradient(
                colors: [
                    Color.platinumRadialCenter,
                    Color.platinumBg,
                    Color.platinumRadialEdge,
                ],
                startPoint: .topLeading,
                endPoint: .bottomTrailing
            )
            .ignoresSafeArea()

            // Soft ambient gray glows — quiet depth, no color.
            Circle()
                .fill(Color.white.opacity(0.55))
                .frame(width: 520, height: 520)
                .blur(radius: 120)
                .offset(x: -220, y: -180)
                .scaleEffect(animate ? 1.1 : 0.95)
                .animation(.easeInOut(duration: 6).repeatForever(autoreverses: true), value: animate)

            Circle()
                .fill(Color.platinumAccent.opacity(0.06))
                .frame(width: 480, height: 480)
                .blur(radius: 140)
                .offset(x: 240, y: 220)
                .scaleEffect(animate ? 0.95 : 1.08)
                .animation(.easeInOut(duration: 7).repeatForever(autoreverses: true), value: animate)

            VStack(spacing: 28) {
                Spacer(minLength: 0)

                // Brand — MW monogram + wordmark
                VStack(spacing: 14) {
                    MWMonogram(size: 68)

                    VStack(spacing: 4) {
                        Text("Matcha Work")
                            .font(.system(size: 30, weight: .bold, design: .rounded))
                            .foregroundColor(Color.platinumText)
                        Text("Your AI workspace for teams and creators.")
                            .font(.system(size: 13))
                            .foregroundColor(Color.platinumSecondary)
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
                                .foregroundColor(.red.opacity(0.9))
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }
                        .padding(10)
                        .background(Color.red.opacity(0.07))
                        .overlay(
                            RoundedRectangle(cornerRadius: 8)
                                .stroke(Color.red.opacity(0.22), lineWidth: 1)
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
                    .foregroundColor(.white)
                    .background(
                        LinearGradient(
                            colors: [Color.platinumAccent, Color.platinumAccentDark],
                            startPoint: .top,
                            endPoint: .bottom
                        )
                        .cornerRadius(10)
                    )
                    .cornerRadius(10)
                    .contentShape(Rectangle())
                    .shadow(color: Color.platinumAccent.opacity(0.25), radius: 10, x: 0, y: 4)
                    .disabled(viewModel.isLoading)
                }
                .padding(28)
                .background(
                    RoundedRectangle(cornerRadius: 16)
                        .fill(Color.platinumCard)
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 16)
                        .stroke(Color.platinumBorder, lineWidth: 1)
                )
                .shadow(color: .black.opacity(0.10), radius: 24, x: 0, y: 10)
                .shadow(color: .black.opacity(0.05), radius: 2, x: 0, y: 1)
                .frame(width: 380)

                Text("v1.0 · \(APIClient.shared.baseURL.replacingOccurrences(of: "https://", with: "").replacingOccurrences(of: "http://", with: ""))")
                    .font(.system(size: 10))
                    .foregroundColor(Color.platinumSecondary.opacity(0.7))

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
                .foregroundColor(Color.platinumSecondary)
            HStack(spacing: 8) {
                Image(systemName: icon)
                    .font(.system(size: 12))
                    .foregroundColor(Color.platinumSecondary.opacity(0.7))
                    .frame(width: 14)
                Group {
                    if isSecure {
                        SecureField(placeholder, text: text)
                    } else {
                        TextField(placeholder, text: text)
                    }
                }
                .textFieldStyle(.plain)
                .foregroundColor(Color.platinumText)
                .font(.system(size: 14))
                .onSubmit { onSubmit?() }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 11)
            .background(Color.platinumBg.opacity(0.6))
            .overlay(
                RoundedRectangle(cornerRadius: 10)
                    .stroke(Color.platinumBorder, lineWidth: 1)
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
            return "Can't reach the server at \(APIClient.shared.baseURL). Start the backend (e.g. `./scripts/dev-remote.sh`) and try again — the app will retry automatically when you focus it."
        }
        return raw
    }
}
