import SwiftUI

struct ProductListView: View {
    let site: CappeSite

    @State private var vm = CatalogListViewModel()
    @State private var showCreate = false
    @State private var showDiscounts = false

    var body: some View {
        Group {
            if vm.isLoading && vm.products.isEmpty {
                ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if vm.products.isEmpty {
                ContentUnavailableView("No products yet", systemImage: "square.grid.2x2", description: Text("Add something to sell or offer."))
            } else {
                List {
                    ForEach(vm.products) { product in
                        NavigationLink {
                            ProductFormView(site: site, existing: product, onSaved: { Task { await vm.load(siteId: site.id) } })
                        } label: {
                            ProductRow(product: product)
                        }
                    }
                    .onDelete { offsets in
                        for index in offsets {
                            let product = vm.products[index]
                            Task { await vm.delete(siteId: site.id, productId: product.id) }
                        }
                    }
                }
                .listStyle(.plain)
            }
        }
        .overlay(alignment: .top) { ErrorBanner(message: vm.error) }
        .background(Color(GummfitTheme.background).ignoresSafeArea())
        .navigationTitle("Catalog")
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Menu {
                    Button("New product") { showCreate = true }
                    Button("Discounts") { showDiscounts = true }
                } label: {
                    Image(systemName: "plus")
                }
            }
        }
        .sheet(isPresented: $showCreate) {
            NavigationStack {
                ProductFormView(site: site, existing: nil, onSaved: { Task { await vm.load(siteId: site.id) } })
            }
        }
        .sheet(isPresented: $showDiscounts) {
            NavigationStack { DiscountsView(site: site) }
        }
        .task { await vm.load(siteId: site.id) }
        .refreshable { await vm.load(siteId: site.id) }
    }
}

private struct ProductRow: View {
    let product: CappeProduct

    var body: some View {
        HStack(spacing: 12) {
            AsyncImage(url: product.image_url.flatMap(URL.init(string:))) { image in
                image.resizable().aspectRatio(contentMode: .fill)
            } placeholder: {
                Rectangle().fill(Color.gray.opacity(0.2))
            }
            .frame(width: 44, height: 44)
            .clipShape(RoundedRectangle(cornerRadius: 8))

            VStack(alignment: .leading, spacing: 2) {
                Text(product.name).font(.subheadline.bold())
                Text(Formatters.cents(product.price_cents, currency: product.currency))
                    .font(.caption)
                    .foregroundStyle(GummfitTheme.textDim)
            }

            Spacer()

            if let inventory = product.inventory {
                Text("\(inventory) in stock")
                    .font(.caption2)
                    .foregroundStyle(inventory == 0 ? .red : GummfitTheme.textDim)
            }
            statusPill
        }
    }

    private var statusPill: some View {
        Text(product.status.capitalized)
            .font(.caption2.bold())
            .padding(.horizontal, 6)
            .padding(.vertical, 3)
            .background(product.status == "active" ? GummfitTheme.accent.opacity(0.2) : Color.gray.opacity(0.2), in: Capsule())
            .foregroundStyle(product.status == "active" ? GummfitTheme.accent : GummfitTheme.textDim)
    }
}
