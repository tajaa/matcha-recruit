import SwiftUI

private let weekdayNames = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

struct AvailabilityView: View {
    let site: CappeSite

    @State private var vm = AvailabilityViewModel()
    @State private var locations: [CappeLocation] = []
    @State private var selectedLocationId: String?

    var body: some View {
        List {
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
            ForEach($vm.slots) { $slot in
                HStack {
                    Picker("Day", selection: $slot.weekday) {
                        ForEach(0..<7, id: \.self) { Text(weekdayNames[$0]).tag($0) }
                    }
                    .frame(width: 90)
                    DatePicker("Start", selection: Binding(
                        get: { Formatters.date(fromTimeString: slot.start_time) },
                        set: { slot.start_time = Formatters.timeString(from: $0) }
                    ), displayedComponents: .hourAndMinute)
                    .labelsHidden()
                    DatePicker("End", selection: Binding(
                        get: { Formatters.date(fromTimeString: slot.end_time) },
                        set: { slot.end_time = Formatters.timeString(from: $0) }
                    ), displayedComponents: .hourAndMinute)
                    .labelsHidden()
                }
            }
            .onDelete { vm.slots.remove(atOffsets: $0) }
            Button("Add window") {
                vm.slots.append(CappeAvailabilitySlot(weekday: 0, start_time: "09:00:00", end_time: "17:00:00"))
            }
        }
        .overlay(alignment: .top) { ErrorBanner(message: vm.error) }
        .navigationTitle("Availability")
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button(vm.isSaving ? "Saving…" : "Save") { Task { await vm.save(siteId: site.id, locationId: selectedLocationId) } }
                    .disabled(vm.isSaving)
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
