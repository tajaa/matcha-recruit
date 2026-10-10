import SwiftUI

/// The Manage tab: what waits for this manager, and the week they run, for
/// one store or (approvals only) all of them.
struct ManageView: View {
    private enum Page: Hashable { case approvals, week }

    @Environment(AppState.self) private var appState
    let scope: ManagerScope
    /// The store being managed; empty is "every store" (business admins with
    /// more than one). Remembered across launches; a store from another
    /// account's scope is ignored.
    @AppStorage("schedule.manage.location") private var storedLocation = ""
    @State private var page: Page = .approvals

    /// The chosen store, or nil for all of them.
    private var location: ManagedLocation? {
        if let match = scope.locations.first(where: { $0.id == storedLocation }) { return match }
        return scope.locations.count == 1 ? scope.locations[0] : nil
    }

    /// A week is always one store's.
    private var weekLocation: ManagedLocation? { location ?? scope.locations.first }

    var body: some View {
        NavigationStack {
            Group {
                switch page {
                case .approvals:
                    ApprovalsView(scope: scope, location: location)
                case .week:
                    if let weekLocation {
                        ManagerWeekView(scope: scope, location: weekLocation).id(weekLocation.id)
                    } else {
                        ContentUnavailableView("No stores yet", systemImage: "storefront",
                                               description: Text("Add a store on the web to start scheduling."))
                    }
                }
            }
            .safeAreaInset(edge: .top, spacing: 0) {
                Picker("Show", selection: $page) {
                    Text(approvalsTitle).tag(Page.approvals)
                    Text("Week").tag(Page.week)
                }
                .pickerStyle(.segmented)
                .padding(.horizontal, 16)
                .padding(.bottom, 8)
                .accessibilityIdentifier("manage.page")
            }
            .navigationTitle("Manage")
            .toolbar {
                if scope.locations.count > 1 {
                    ToolbarItem(placement: .topBarLeading) { storePicker }
                }
            }
        }
        .onChange(of: appState.pendingApprovalID) { _, id in
            if id != nil { page = .approvals }
        }
    }

    private var approvalsTitle: String {
        appState.pendingApprovals > 0 ? "Approvals (\(appState.pendingApprovals))" : "Approvals"
    }

    private var storePicker: some View {
        Menu {
            Picker("Store", selection: $storedLocation) {
                // A week is one store's, so "all" only makes sense for approvals.
                if page == .approvals { Text("All stores").tag("") }
                ForEach(scope.locations) { Text($0.displayName).tag($0.id) }
            }
        } label: {
            Label(page == .week ? (weekLocation?.displayName ?? "Store") : (location?.displayName ?? "All stores"),
                  systemImage: "storefront")
                .labelStyle(.titleAndIcon)
                .font(.app(.subheadline, .medium))
        }
        .accessibilityIdentifier("manage.store")
    }
}
