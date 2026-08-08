import SwiftUI

struct InventoryLogView: View {
    let site: CappeSite
    let productId: String

    @State private var entries: [CappeInventoryAdjustment] = []
    @State private var isLoading = false

    var body: some View {
        Group {
            if isLoading && entries.isEmpty {
                ProgressView()
            } else if entries.isEmpty {
                ContentUnavailableView("No stock changes yet", systemImage: "clock.arrow.circlepath")
            } else {
                List(entries) { entry in
                    VStack(alignment: .leading, spacing: 2) {
                        HStack {
                            Text(entry.delta > 0 ? "+\(entry.delta)" : "\(entry.delta)")
                                .font(.subheadline.bold())
                                .foregroundStyle(entry.delta > 0 ? GummfitTheme.accent : .red)
                            Text(entry.reason.capitalized).font(.caption).foregroundStyle(GummfitTheme.textDim)
                            Spacer()
                            if let balance = entry.balance_after {
                                Text("→ \(balance)").font(.caption).foregroundStyle(GummfitTheme.textDim)
                            }
                        }
                        if let note = entry.note, !note.isEmpty {
                            Text(note).font(.caption)
                        }
                    }
                }
            }
        }
        .navigationTitle("Inventory log")
        .task {
            isLoading = true
            entries = (try? await CatalogService.shared.inventoryLog(siteId: site.id, productId: productId)) ?? []
            isLoading = false
        }
    }
}
