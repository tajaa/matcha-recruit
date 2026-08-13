import SwiftUI

struct CampaignFormSheet: View {
    @Bindable var vm: CampaignsViewModel
    @Environment(\.dismiss) private var dismiss
    let onCreated: (PromoCampaign) -> Void

    @State private var draft = PromoCampaignDraft()
    @State private var validationError: String?

    var body: some View {
        NavigationStack {
            Form {
                Section("Campaign") {
                    TextField("Title", text: $draft.title)
                    TextField("Reward", text: $draft.rewardText, axis: .vertical)
                    TextField("Description (optional)", text: $draft.description, axis: .vertical)
                }

                Section("Claim settings") {
                    TextField("Claim limit", text: $draft.maxClaims)
                        .keyboardType(.numberPad)
                    TextField("Card valid for (days)", text: $draft.expiryDays)
                        .keyboardType(.numberPad)
                    Toggle("Set an end date", isOn: $draft.hasEndDate)
                    if draft.hasEndDate {
                        DatePicker(
                            "Ends",
                            selection: $draft.endDate,
                            in: Date()...,
                            displayedComponents: [.date, .hourAndMinute]
                        )
                    }
                }

                if let validationError {
                    Section {
                        Text(validationError)
                            .foregroundStyle(.red)
                            .font(.footnote)
                    }
                }

                if let error = vm.error {
                    Section {
                        Text(error)
                            .foregroundStyle(.red)
                            .font(.footnote)
                    }
                }
            }
            .navigationTitle("New campaign")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Create") { Task { await submit() } }
                        .disabled(vm.isCreating)
                }
            }
        }
        .presentationDetents([.large])
        .onAppear { vm.error = nil }
    }

    private func submit() async {
        validationError = nil
        vm.error = nil

        do {
            let body = try draft.validated()
            guard let created = await vm.create(body) else { return }
            dismiss()
            onCreated(created)
        } catch let error as PromoCampaignValidationError {
            validationError = error.localizedDescription
        } catch {
            validationError = error.localizedDescription
        }
    }
}
