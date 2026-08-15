import SwiftUI

struct BrandListingsView: View {
    @State private var vm = BrandListingsViewModel()
    @State private var editingListing: Listing?
    @State private var showNew = false
    @State private var pendingDelete: Listing?

    var body: some View {
        Group {
            if vm.listings.isEmpty && !vm.isLoading {
                EmptyState(icon: "gift", title: "No rewards yet", hint: "Add one to get started.")
            } else {
                List(vm.listings) { listing in
                    NavigationLink {
                        ListingRedemptionsView(listing: listing)
                    } label: {
                        VStack(alignment: .leading, spacing: 4) {
                            HStack {
                                Text(listing.title).font(.interSubheadline.bold())
                                    .foregroundStyle(listing.is_active ? .primary : .secondary)
                                Spacer()
                                StatusChip(text: listing.visibility.rawValue)
                            }
                            Text("\(listing.points_cost) pts · \(listing.quantity_claimed) claimed" +
                                 (listing.quantity_total.map { " / \($0)" } ?? ""))
                                .font(.interCaption).foregroundStyle(.secondary)
                        }
                    }
                    .swipeActions {
                        Button("Delete", role: .destructive) { pendingDelete = listing }
                        Button(listing.is_active ? "Deactivate" : "Activate") {
                            Task { await vm.toggleActive(listing) }
                        }.tint(.orange)
                        Button("Edit") { editingListing = listing }.tint(.blue)
                    }
                }
                .listStyle(.plain)
            }
        }
        .navigationTitle("Listings")
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button { showNew = true } label: { Image(systemName: "plus") }
            }
        }
        .task { await vm.load() }
        .refreshable { await vm.load() }
        .overlay(alignment: .top) { ErrorBanner(message: vm.error).padding(.top, 8) }
        .sheet(isPresented: $showNew) { ListingFormSheet(vm: vm) }
        .sheet(item: $editingListing) { listing in ListingFormSheet(vm: vm, editing: listing) }
        .confirmationDialog("Delete this reward?", isPresented: Binding(
            get: { pendingDelete != nil }, set: { if !$0 { pendingDelete = nil } }
        ), titleVisibility: .visible) {
            Button("Delete", role: .destructive) {
                if let listing = pendingDelete { Task { await vm.delete(id: listing.id) } }
                pendingDelete = nil
            }
        }
    }
}
