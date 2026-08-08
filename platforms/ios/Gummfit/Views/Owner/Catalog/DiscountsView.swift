import SwiftUI

struct DiscountsView: View {
    let site: CappeSite

    @Environment(\.dismiss) private var dismiss
    @State private var vm = DiscountsViewModel()
    @State private var locations: [CappeLocation] = []
    @State private var selectedLocationId: String?

    var body: some View {
        Form {
            ErrorBanner(message: vm.error)
            if site.is_multi_location {
                Picker("Location", selection: $selectedLocationId) {
                    Text("All locations").tag(String?.none)
                    ForEach(locations) { location in
                        Text(location.name).tag(String?.some(location.id))
                    }
                }
                .onChange(of: selectedLocationId) { _, newValue in
                    Task { await vm.load(siteId: site.id, locationId: newValue) }
                }
            }
            ForEach($vm.discounts) { $discount in
                Section {
                    TextField("Label", text: $discount.label)
                    Stepper("\(discount.percent_off)% off", value: $discount.percent_off, in: 1...90)
                    Picker("Applies to", selection: $discount.scope) {
                        Text("Everything").tag(DiscountScope.all)
                        Text("A booking type").tag(DiscountScope.booking_type)
                        Text("A product").tag(DiscountScope.product)
                    }
                    .onChange(of: discount.scope) { _, _ in discount.target_id = nil }
                    if discount.scope == .booking_type {
                        Picker("Booking type", selection: Binding(
                            get: { discount.target_id ?? "" },
                            set: { discount.target_id = $0.isEmpty ? nil : $0 }
                        )) {
                            Text("Choose one").tag("")
                            ForEach(vm.bookingTypes) { type in
                                Text(type.name).tag(type.id)
                            }
                        }
                    } else if discount.scope == .product {
                        Picker("Product", selection: Binding(
                            get: { discount.target_id ?? "" },
                            set: { discount.target_id = $0.isEmpty ? nil : $0 }
                        )) {
                            Text("Choose one").tag("")
                            ForEach(vm.products) { product in
                                Text(product.name).tag(product.id)
                            }
                        }
                    }
                    Toggle("Active", isOn: $discount.active)
                }
            }
            .onDelete { vm.discounts.remove(atOffsets: $0) }
            Section {
                Button("Add discount") {
                    vm.discounts.append(CappeDiscountInput(percent_off: 10))
                }
            }
        }
        .navigationTitle("Discounts")
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button(vm.isSaving ? "Saving…" : "Save") {
                    Task {
                        if await vm.save(siteId: site.id, locationId: selectedLocationId) { dismiss() }
                    }
                }
                .disabled(vm.isSaving || !vm.canSave)
            }
            ToolbarItem(placement: .cancellationAction) {
                Button("Cancel") { dismiss() }
            }
        }
        .task {
            await vm.load(siteId: site.id, locationId: selectedLocationId)
            if site.is_multi_location {
                locations = (try? await VenueService.shared.listLocations(siteId: site.id)) ?? []
            }
        }
    }
}
