import SwiftUI

struct RedeemConfirmSheet: View {
    let listing: Listing
    @Bindable var vm: MarketplaceViewModel
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            VStack(spacing: 20) {
                Text(listing.title).font(.title2.bold())
                if let description = listing.description {
                    Text(description).foregroundStyle(.secondary)
                }
                PointsPill(points: listing.points_cost)
                if let terms = listing.terms {
                    Text(terms).font(.caption).foregroundStyle(.secondary)
                }

                ErrorBanner(message: vm.error)

                if let redemption = vm.lastRedemption {
                    VStack(spacing: 8) {
                        Text("Redeemed!").font(.headline).foregroundStyle(.green)
                        if let code = redemption.code {
                            Text(code).font(.system(.title3, design: .monospaced))
                        }
                    }
                    Button("Done") { dismiss() }
                        .frame(maxWidth: .infinity).padding()
                        .background(.tint, in: RoundedRectangle(cornerRadius: 10))
                        .foregroundStyle(.white)
                } else {
                    Button {
                        Task { await vm.redeem(listing) }
                    } label: {
                        Text("Redeem for \(listing.points_cost) points").bold()
                    }
                    .frame(maxWidth: .infinity).padding()
                    .background(.tint, in: RoundedRectangle(cornerRadius: 10))
                    .foregroundStyle(.white)
                }
            }
            .padding()
            .navigationTitle("Confirm redemption")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Close") { dismiss() } }
            }
        }
        .presentationDetents([.medium])
    }
}
