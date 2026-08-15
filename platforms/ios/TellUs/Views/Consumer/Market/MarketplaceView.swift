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
                    // Redeem button and LikeButton are siblings, not nested —
                    // a Button inside another Button's label swallows the
                    // inner tap. Both carry .plain/.borderless styles so the
                    // List row doesn't treat the whole cell as one hit target.
                    HStack(spacing: 12) {
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
                                    Text(listing.title).font(.headline).foregroundStyle(.white.opacity(0.92))
                                    if let brand = listing.brand_name {
                                        Text(brand).font(.caption).foregroundStyle(TU.textDim)
                                    }
                                    PointsPill(points: listing.points_cost)
                                }
                                Spacer()
                                if listing.quantity_remaining == 0 {
                                    StatusChip(text: "Sold out", tint: TU.textDim)
                                }
                            }
                        }
                        .buttonStyle(.plain)
                        .disabled(listing.quantity_remaining == 0)

                        LikeButton(
                            target: .listing, id: listing.id,
                            count: listing.likeCount, liked: listing.likedByMe,
                            onError: { vm.error = $0 }
                        )
                    }
                    .themedRow()
                }
                .listStyle(.insetGrouped)
                .themedScreen()
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
