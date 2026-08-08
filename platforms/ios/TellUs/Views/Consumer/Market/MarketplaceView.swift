import SwiftUI

struct MarketplaceView: View {
    @Environment(AppState.self) private var appState
    @State private var vm = MarketplaceViewModel()
    @State private var selected: Listing?

    var body: some View {
        Group {
            if vm.listings.isEmpty && !vm.isLoading {
                EmptyState(icon: "gift", title: "No rewards yet", hint: "Check back soon.")
            } else {
                List(vm.listings) { listing in
                    Button {
                        vm.redeemFlow.begin()
                        selected = listing
                    } label: {
                        HStack(spacing: 12) {
                            if let urlString = listing.image_url, let url = URL(string: urlString) {
                                AsyncImage(url: url) { image in
                                    image.resizable().scaledToFill()
                                } placeholder: {
                                    Color.gray.opacity(0.15)
                                }
                                .frame(width: 56, height: 56)
                                .clipShape(RoundedRectangle(cornerRadius: 8))
                            }
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
        .sheet(item: $selected, onDismiss: {
            if vm.redeemFlow.lastRedemption != nil { Task { await vm.load() } }
        }) { listing in
            RedeemConfirmSheet(listing: listing, flow: vm.redeemFlow)
        }
        .task {
            // Seeds from the account's city on first load so a Settings
            // location change (ConsumerSettingsView) actually narrows
            // results next time this tab is opened.
            if vm.city == nil { vm.city = appState.account?.city }
            await vm.load()
        }
        .refreshable { await vm.load() }
        .overlay(alignment: .top) { ErrorBanner(message: vm.error).padding(.top, 8) }
    }
}
