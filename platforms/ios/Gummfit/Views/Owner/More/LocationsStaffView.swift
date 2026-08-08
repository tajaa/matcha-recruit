import SwiftUI

/// Multi-location sites only — listed in More behind `site.is_multi_location`.
struct LocationsStaffView: View {
    let site: CappeSite

    @State private var vm = VenueViewModel()
    @State private var newLocationName = ""
    @State private var newStaffName = ""
    @State private var showNewLocation = false
    @State private var showNewStaff = false

    var body: some View {
        List {
            Section("Locations") {
                ForEach(vm.locations) { location in
                    VStack(alignment: .leading, spacing: 2) {
                        Text(location.name).font(.subheadline.bold())
                        if let address = location.address { Text(address).font(.caption).foregroundStyle(GummfitTheme.textDim) }
                    }
                }
                .onDelete { offsets in
                    for index in offsets {
                        let location = vm.locations[index]
                        Task { await vm.deleteLocation(siteId: site.id, locationId: location.id) }
                    }
                }
                Button("Add location") { showNewLocation = true }
            }
            Section("Staff") {
                ForEach(vm.staff) { member in
                    HStack {
                        Text(member.name)
                        Spacer()
                        if !member.active { Text("Inactive").font(.caption2).foregroundStyle(GummfitTheme.textDim) }
                    }
                }
                .onDelete { offsets in
                    for index in offsets {
                        let member = vm.staff[index]
                        Task { await vm.deleteStaff(siteId: site.id, staffId: member.id) }
                    }
                }
                Button("Add staff member") { showNewStaff = true }
            }
        }
        .overlay(alignment: .top) { ErrorBanner(message: vm.error) }
        .navigationTitle("Locations & Staff")
        .alert("New location", isPresented: $showNewLocation) {
            TextField("Name", text: $newLocationName)
            Button("Add") {
                Task {
                    await vm.createLocation(siteId: site.id, CappeLocationCreate(name: newLocationName))
                    newLocationName = ""
                }
            }
            Button("Cancel", role: .cancel) {}
        }
        .alert("New staff member", isPresented: $showNewStaff) {
            TextField("Name", text: $newStaffName)
            Button("Add") {
                Task {
                    await vm.createStaff(siteId: site.id, CappeStaffCreate(name: newStaffName))
                    newStaffName = ""
                }
            }
            Button("Cancel", role: .cancel) {}
        }
        .task { await vm.load(siteId: site.id) }
    }
}
