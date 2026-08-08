import SwiftUI

struct BookingTypesView: View {
    let site: CappeSite

    @State private var vm = BookingTypesViewModel()
    @State private var showCreate = false
    @State private var newName = ""
    @State private var newDuration = 30
    @State private var newPriceCents = 0

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
            NavigationStack {
                Form {
                    TextField("Name", text: $newName)
                    Stepper("\(newDuration) minutes", value: $newDuration, in: 5...480, step: 5)
                    HStack {
                        Text("Price")
                        Spacer()
                        TextField("0.00", value: Binding(
                            get: { Double(newPriceCents) / 100 },
                            set: { newPriceCents = Int(($0 * 100).rounded()) }
                        ), format: .number.precision(.fractionLength(2)))
                            .keyboardType(.decimalPad)
                    }
                }
                .navigationTitle("New booking type")
                .toolbar {
                    ToolbarItem(placement: .topBarTrailing) {
                        Button("Save") {
                            Task {
                                await vm.create(siteId: site.id, CappeBookingTypeCreate(name: newName, duration_minutes: newDuration, price_cents: newPriceCents))
                                newName = ""; newDuration = 30; newPriceCents = 0
                                showCreate = false
                            }
                        }
                        .disabled(newName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    }
                }
            }
        }
        .task { await vm.load(siteId: site.id) }
    }
}
