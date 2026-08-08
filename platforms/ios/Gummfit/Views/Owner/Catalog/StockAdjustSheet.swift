import SwiftUI

struct StockAdjustSheet: View {
    let site: CappeSite
    let product: CappeProduct
    /// Live in-form balance (may already reflect an unsaved edit or an
    /// earlier adjust this session) rather than `product.inventory`, which
    /// is a stale snapshot from whenever the form loaded.
    let currentInventory: Int
    var onAdjusted: (CappeProduct) -> Void = { _ in }

    @Environment(\.dismiss) private var dismiss
    @State private var vm = StockAdjustViewModel()

    private var current: Int { currentInventory }

    var body: some View {
        Form {
            ErrorBanner(message: vm.error)
            Section {
                Stepper("Delta: \(vm.delta > 0 ? "+" : "")\(vm.delta)", value: $vm.delta, in: -10000...10000)
                HStack {
                    Text("New balance")
                    Spacer()
                    Text("\(StockAdjustViewModel.preview(current: current, delta: vm.delta))")
                        .font(.headline)
                }
            }
            Section("Reason") {
                Picker("Reason", selection: $vm.reason) {
                    Text("Manual").tag("manual")
                    Text("Restock").tag("restock")
                    Text("Damage").tag("damage")
                    Text("Return").tag("return")
                    Text("Adjustment").tag("adjustment")
                }
                TextField("Note", text: $vm.note, axis: .vertical)
            }
        }
        .navigationTitle("Adjust stock")
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button(vm.isSaving ? "Saving…" : "Save") {
                    Task {
                        if let updated = await vm.submit(siteId: site.id, productId: product.id) {
                            onAdjusted(updated)
                            dismiss()
                        }
                    }
                }
                .disabled(vm.isSaving || vm.delta == 0)
            }
            ToolbarItem(placement: .cancellationAction) {
                Button("Cancel") { dismiss() }
            }
        }
    }
}
