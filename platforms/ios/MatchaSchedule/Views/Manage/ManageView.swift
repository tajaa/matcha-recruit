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
                .safeAreaInset(edge: .top, spacing: 0) {
                    if scope.locations.count > 1 {
                        storePicker.padding(.horizontal, 16).padding(.bottom, 8)
                    }
                }
                .navigationTitle("Manage")
        }
    }

    /// Under the title rather than in the toolbar: iOS 26 draws a toolbar menu
    /// as its icon alone, which hid which store was showing.
    private var storePicker: some View {
        Menu {
            Picker("Store", selection: $storedLocation) {
                Text("All stores").tag("")
                ForEach(scope.locations) { Text($0.displayName).tag($0.id) }
            }
        } label: {
            StorePickerLabel(name: location?.displayName ?? "All stores")
        }
        .accessibilityIdentifier("manage.store")
    }
}

struct StorePickerLabel: View {
    let name: String

    var body: some View {
        HStack(spacing: 6) {
            Image(systemName: "storefront")
            Text(name).lineLimit(1)
            Image(systemName: "chevron.up.chevron.down").font(.caption2)
        }
        .font(.app(.subheadline, .medium))
        .foregroundStyle(.primary)
        .frame(maxWidth: .infinity, alignment: .leading)
        .contentShape(Rectangle())
    }
}
