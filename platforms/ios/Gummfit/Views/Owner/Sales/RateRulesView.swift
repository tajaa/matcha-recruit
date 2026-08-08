import SwiftUI

struct RateRulesView: View {
    let site: CappeSite

    @State private var vm = RateRulesViewModel()
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
            ForEach($vm.rules) { $rule in
                VStack(alignment: .leading) {
                    TextField("Label", text: $rule.label)
                    HStack {
                        DatePicker("Start", selection: Binding(
                            get: { Formatters.date(fromTimeString: rule.start_time) },
                            set: { rule.start_time = Formatters.timeString(from: $0) }
                        ), displayedComponents: .hourAndMinute)
                        .labelsHidden()
                        DatePicker("End", selection: Binding(
                            get: { Formatters.date(fromTimeString: rule.end_time) },
                            set: { rule.end_time = Formatters.timeString(from: $0) }
                        ), displayedComponents: .hourAndMinute)
                        .labelsHidden()
                        TextField("×", value: $rule.multiplier, format: .number)
                            .keyboardType(.decimalPad)
                            .frame(width: 50)
                    }
                }
            }
            .onDelete { vm.rules.remove(atOffsets: $0) }
            Button("Add rule") {
                vm.rules.append(CappeRateRuleInput(label: "Peak", start_time: "17:00:00", end_time: "20:00:00", multiplier: 1.5))
            }
        }
        .overlay(alignment: .top) { ErrorBanner(message: vm.error) }
        .navigationTitle("Rate rules")
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button(vm.isSaving ? "Saving…" : "Save") { Task { await vm.save(siteId: site.id, locationId: selectedLocationId) } }
                    .disabled(vm.isSaving)
            }
        }
        .task {
            await vm.load(siteId: site.id, locationId: selectedLocationId)
            if site.is_multi_location {
                do { locations = try await VenueService.shared.listLocations(siteId: site.id) }
                catch { if !error.isCancellation { vm.error = error.localizedDescription } }
            }
        }
    }
}
