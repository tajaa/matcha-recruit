import SwiftUI

struct BookingTypesView: View {
    let site: CappeSite

    @State private var vm = BookingTypesViewModel()
    @State private var showCreate = false

    var body: some View {
        List {
            ForEach(vm.types) { type in
                VStack(alignment: .leading, spacing: 2) {
                    HStack {
                        Text(type.name).font(.subheadline.bold())
                        Spacer()
                        if let price = type.price_cents { Text(Formatters.cents(price)).font(.caption) }
                    }
                    Text("\(type.duration_minutes) min").font(.caption).foregroundStyle(GummfitTheme.textDim)
                }
                .swipeActions {
                    Button("Delete", role: .destructive) {
                        Task { await vm.delete(siteId: site.id, typeId: type.id) }
                    }
                }
            }
        }
        .overlay(alignment: .top) { ErrorBanner(message: vm.error) }
        .navigationTitle("Booking types")
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button("Add", systemImage: "plus") { showCreate = true }
            }
        }
        .sheet(isPresented: $showCreate) {
            BookingTypeCreateSheet(siteId: site.id) { created in
                vm.types.insert(created, at: 0)
            }
        }
        .task { await vm.load(siteId: site.id) }
    }
}
