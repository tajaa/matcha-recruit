import SwiftUI

/// Extracts a reset token from a pasted web link (…/tellus/reset-password?token=…,
/// a query param not a path segment — unlike intake's /i/{token}) or a bare
/// token. Pure function, unit-tested in Tests/ResetTokenTests.swift.
func resetToken(from raw: String) -> String? {
    let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
    if let components = URLComponents(string: trimmed),
       let token = components.queryItems?.first(where: { $0.name == "token" })?.value,
       !token.isEmpty {
        return token
    }
    // Server enforces min_length=16 on the token itself.
    let range = trimmed.range(of: "^[A-Za-z0-9_-]{16,}$", options: .regularExpression)
    return range != nil ? trimmed : nil
}

/// Tokens are admin-minted only (no self-serve request endpoint — backend
/// gap, flagged in the PR). This screen just consumes one, mirroring web's
/// ResetPassword.tsx.
struct ResetPasswordView: View {
    @Environment(\.dismiss) private var dismiss
    @State private var pastedLink = ""
    @State private var password = ""
    @State private var confirm = ""
    @State private var error: String?
    @State private var isSubmitting = false
    @State private var done = false

    private var resolvedToken: String? { resetToken(from: pastedLink) }

    var body: some View {
        NavigationStack {
            Form {
                if done {
                    Section {
                        Text("Password updated. You can sign in with your new password now.")
                            .foregroundStyle(.green)
                    }
                } else {
                    Section {
                        TextField("Paste reset link or token", text: $pastedLink)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                    }
                    Section {
                        SecureField("New password", text: $password)
                        SecureField("Confirm password", text: $confirm)
                    }
                    if let error {
                        Section { Text(error).foregroundStyle(.red).font(.footnote) }
                    }
                    Section {
                        Button {
                            Task { await submit() }
                        } label: {
                            if isSubmitting { ProgressView() } else { Text("Reset password").bold() }
                        }
                        .disabled(resolvedToken == nil || password.count < 8 || password != confirm || isSubmitting)
                    }
                }
            }
            .navigationTitle("Reset password")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button(done ? "Done" : "Cancel") { dismiss() } }
            }
        }
    }

    private func submit() async {
        guard let token = resolvedToken else { return }
        guard password.count >= 8 else { error = "Password must be at least 8 characters."; return }
        guard password == confirm else { error = "Passwords don't match."; return }
        isSubmitting = true; defer { isSubmitting = false }
        error = nil
        do {
            try await AuthService.shared.resetPassword(token: token, newPassword: password)
            done = true
        } catch {
            if error.isCancellation { return }
            self.error = error.localizedDescription
        }
    }
}
