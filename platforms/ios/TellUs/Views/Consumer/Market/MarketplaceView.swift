import SwiftUI

struct MarketplaceView: View {
    @State private var vm = MarketplaceViewModel()
    @State private var selected: Listing?

    var body: some View {
        Group {
            if vm.listings.isEmpty && !vm.isLoading {
                EmptyState(icon: "gift", title: "No rewards yet", hint: "Check back soon.")
            } else {
                List(vm.listings) { listing in
                    Button { selected = listing } label: {
                        HStack(spacing: 12) {
                            VStack(alignment: .leading, spacing: 4) {
                                Text(listing.title).font(.headline).foregroundStyle(.primary)
                                if let brand = listing.brand_name {
                                    Text(brand).font(.caption).foregroundStyle(.secondary)
                                }
                                PointsPill(points: listing.points_cost)
                            }
                            Spacer()
                            if listing.quantity_remaining == 0 {
                                StatusChip(text: "Sold out", tint: .gray)
                            }
                        }
                    }
                    .disabled(listing.quantity_remaining == 0)
                }
                .listStyle(.plain)
            }
        }
        .sheet(item: $selected) { listing in
            RedeemConfirmSheet(listing: listing, vm: vm)
        }
        .task { await vm.load() }
        .refreshable { await vm.load() }
        .overlay(alignment: .top) { ErrorBanner(message: vm.error).padding(.top, 8) }
    }
}
