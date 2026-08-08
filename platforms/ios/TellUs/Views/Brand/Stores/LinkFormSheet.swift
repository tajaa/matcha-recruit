import SwiftUI

struct LinkFormSheet: View {
    @Bindable var vm: StoresViewModel
    @Environment(\.dismiss) private var dismiss

    @State private var storeId: String?
    @State private var label = ""
    @State private var maxUses = ""
    @State private var expiresAt = Date().addingTimeInterval(86_400 * 90)
    @State private var hasExpiry = false

    private static let iso = ISO8601DateFormatter()

    var body: some View {
        NavigationStack {
            Form {
                Picker("Store", selection: $storeId) {
                    Text("Any store").tag(String?.none)
                    ForEach(vm.stores) { store in
                        Text(store.name).tag(Optional(store.id))
                    }
                }
                TextField("Label (optional)", text: $label)
                TextField("Max uses (optional)", text: $maxUses)
                    .keyboardType(.numberPad)
                Toggle("Expires", isOn: $hasExpiry)
                if hasExpiry {
                    DatePicker("Expires at", selection: $expiresAt, displayedComponents: .date)
                }
                if let error = vm.error {
                    Text(error).foregroundStyle(.red).font(.footnote)
                }
            }
            .navigationTitle("New link")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Create") {
                        Task {
                            await vm.createLink(LinkCreate(
                                store_id: storeId,
                                label: label.isEmpty ? nil : label,
                                max_uses: Int(maxUses),
                                expires_at: hasExpiry ? Self.iso.string(from: expiresAt) : nil
                            ))
                            dismiss()
                        }
                    }
                }
            }
        }
    }
}
