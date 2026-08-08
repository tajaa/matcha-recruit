import SwiftUI

struct NewThreadSheet: View {
    let site: CappeSite
    var onStarted: () -> Void = {}

    @Environment(\.dismiss) private var dismiss
    @State private var email = ""
    @State private var name = ""
    @State private var subject = ""
    @State private var messageBody = ""
    @State private var isSending = false
    @State private var error: String?

    var canSubmit: Bool {
        !email.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            && !messageBody.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            && !isSending
    }

    var body: some View {
        Form {
            ErrorBanner(message: error)
            Section("Client") {
                TextField("Email", text: $email)
                    .keyboardType(.emailAddress)
                    .textInputAutocapitalization(.never)
                TextField("Name (optional)", text: $name)
            }
            Section("Message") {
                TextField("Subject (optional)", text: $subject)
                TextField("Message", text: $messageBody, axis: .vertical)
            }
        }
        .navigationTitle("New conversation")
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button(isSending ? "Sending…" : "Send") { Task { await submit() } }
                    .disabled(!canSubmit)
            }
            ToolbarItem(placement: .cancellationAction) {
                Button("Cancel") { dismiss() }
            }
        }
    }

    private func submit() async {
        guard canSubmit else { return }
        isSending = true
        error = nil
        defer { isSending = false }
        do {
            _ = try await MessagesService.shared.startThread(siteId: site.id, CappeThreadCreate(
                client_email: email.trimmingCharacters(in: .whitespacesAndNewlines),
                client_name: name.isEmpty ? nil : name,
                subject: subject.isEmpty ? nil : subject,
                body: messageBody
            ))
            onStarted()
            dismiss()
        } catch {
            if error.isCancellation { return }
            self.error = error.localizedDescription
        }
    }
}
