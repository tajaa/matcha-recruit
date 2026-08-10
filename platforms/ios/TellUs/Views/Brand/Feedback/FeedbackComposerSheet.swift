import SwiftUI

struct FeedbackComposerSheet: View {
    let reportId: String
    let onStarted: (DmThread) -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var body = ""
    @State private var isSending = false
    @State private var error: String?

    var body: some View {
        NavigationStack {
            Form {
                Section("Message reporter") {
                    TextEditor(text: $body).frame(minHeight: 140)
                }
                if let error { Text(error).foregroundStyle(.red) }
            }
            .navigationTitle("New message")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button {
                        Task { await send() }
                    } label: {
                        if isSending { ProgressView() } else { Text("Send") }
                    }
                    .disabled(body.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || isSending)
                }
            }
        }
    }

    private func send() async {
        let text = body.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        isSending = true
        defer { isSending = false }
        do {
            let thread = try await DmService.shared.openFeedbackThread(reportId: reportId, body: text)
            onStarted(thread)
            dismiss()
        } catch {
            if !error.isCancellation { self.error = error.localizedDescription }
        }
    }
}
