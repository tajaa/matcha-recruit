import SwiftUI

struct FriendReportSheet: View {
    let accountId: String
    @Environment(\.dismiss) private var dismiss
    @State private var reason = "spam"
    @State private var detail = ""
    @State private var error: String?
    @State private var isSubmitting = false

    private let reasons = ["spam", "harassment", "impersonation", "inappropriate", "other"]

    var body: some View {
        NavigationStack {
            Form {
                Picker("Reason", selection: $reason) {
                    ForEach(reasons, id: \.self) { Text($0.capitalized).tag($0) }
                }
                TextEditor(text: $detail)
                    .frame(minHeight: 120)
                    .overlay(alignment: .topLeading) {
                        if detail.isEmpty { Text("Optional details").foregroundStyle(TU.textDim).padding(.top, 8).padding(.leading, 5) }
                    }
                if let error { Text(error).foregroundStyle(.red).font(.interFootnote) }
            }
            .navigationTitle("Report Person")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Submit") {
                        isSubmitting = true
                        Task {
                            do {
                                try await FriendsService.shared.report(accountId: accountId, reason: reason, detail: detail.isEmpty ? nil : detail)
                                dismiss()
                            } catch {
                                self.error = error.localizedDescription
                                isSubmitting = false
                            }
                        }
                    }
                    .disabled(isSubmitting)
                }
            }
        }
    }
}
