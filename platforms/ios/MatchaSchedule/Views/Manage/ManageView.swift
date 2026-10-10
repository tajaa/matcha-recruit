import SwiftUI

/// The Manage tab: what waits for this manager, for one store or all of them.
struct ManageView: View {
    let scope: ManagerScope
    /// The store being managed; empty is "every store" (business admins with
    /// more than one). Remembered across launches; a store from another
    /// account's scope is ignored.
    @AppStorage("schedule.manage.location") private var storedLocation = ""

    private var location: ManagedLocation? {
        if let match = scope.locations.first(where: { $0.id == storedLocation }) { return match }
        return scope.locations.count == 1 ? scope.locations[0] : nil
    }

    var body: some View {
        NavigationStack {
            ApprovalsView(scope: scope, location: location)
                .navigationTitle("Manage")
                .toolbar {
                    if scope.locations.count > 1 {
                        ToolbarItem(placement: .topBarTrailing) { storePicker }
                    }
                }
        }
    }

    private var storePicker: some View {
        Menu {
            Picker("Store", selection: $storedLocation) {
                Text("All stores").tag("")
                ForEach(scope.locations) { Text($0.displayName).tag($0.id) }
            }
        } label: {
            Label(location?.displayName ?? "All stores", systemImage: "storefront")
                .labelStyle(.titleAndIcon)
                .font(.app(.subheadline, .medium))
        }
        .accessibilityIdentifier("manage.store")
    }
}
