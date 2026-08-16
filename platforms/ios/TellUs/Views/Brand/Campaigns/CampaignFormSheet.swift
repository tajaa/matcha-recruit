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
                    Picker("Type", selection: $draft.campaignType) {
                        Text("QR campaign").tag("qr")
                        Text("Location campaign").tag("location")
                    }
                }

                if draft.campaignType == "location" {
                    Section("Location audience") {
                        Picker("Store", selection: Binding(
                            get: { draft.storeID ?? "" },
                            set: { draft.storeID = $0.isEmpty ? nil : $0 }
                        )) {
                            Text("Choose a store").tag("")
                            ForEach(vm.stores) { store in
                                Text(store.name).tag(store.id)
                            }
                        }
                        VStack(alignment: .leading) {
                            Text("Push radius: \(draft.radiusMiles, specifier: "%.1f") miles")
                            Slider(value: $draft.radiusMiles, in: 1...10, step: 0.5)
                        }
                        Text("Only followers with a fresh device location inside this radius can receive and claim the offer.")
                            .font(.interCaption)
                            .foregroundStyle(.secondary)
                    }
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
                            .font(.interFootnote)
                    }
                }

                if let error = vm.error {
                    Section {
                        Text(error)
                            .foregroundStyle(.red)
                            .font(.interFootnote)
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
            onCreated(created)
        } catch let error as PromoCampaignValidationError {
            validationError = error.localizedDescription
        } catch {
            validationError = error.localizedDescription
        }
    }
}
