import SwiftUI

@MainActor
@Observable
final class ListingRedemptionsViewModel: LoadableVM {
    let listingId: String
    var redemptions: [Redemption] = []
    var isLoading = false
    var error: String?

    init(listingId: String) { self.listingId = listingId }

    func load() async {
        await withLoad {
            redemptions = try await BrandAdminService.shared.listingRedemptions(id: listingId)
        }
    }

    func markClaimed(_ id: String) async {
        await withLoad {
            let updated = try await BrandAdminService.shared.updateRedemption(id: id, status: "redeemed")
            if let idx = redemptions.firstIndex(where: { $0.id == id }) { redemptions[idx] = updated }
        }
    }
}

struct ListingRedemptionsView: View {
    let listing: Listing
    @State private var vm: ListingRedemptionsViewModel

    init(listing: Listing) {
        self.listing = listing
        _vm = State(initialValue: ListingRedemptionsViewModel(listingId: listing.id))
    }

    var body: some View {
        Group {
            if vm.redemptions.isEmpty && !vm.isLoading {
                EmptyState(icon: "ticket", title: "No redemptions yet")
            } else {
                List(vm.redemptions) { redemption in
                    HStack {
                        VStack(alignment: .leading) {
                            if let code = redemption.code {
                                Text(code).font(.system(.subheadline, design: .monospaced))
                            }
                            Text(Formatters.relativeString(from: redemption.created_at))
                                .font(.interCaption2).foregroundStyle(.secondary)
                        }
                        Spacer()
                        StatusChip(text: redemption.status.rawValue)
                        if redemption.status == .issued {
                            Button("Mark claimed") { Task { await vm.markClaimed(redemption.id) } }
                                .buttonStyle(.bordered)
                        }
                    }
                }
                .listStyle(.plain)
            }
        }
        .navigationTitle(listing.title)
        .task { await vm.load() }
        .refreshable { await vm.load() }
        .overlay(alignment: .top) { ErrorBanner(message: vm.error).padding(.top, 8) }
    }
}
