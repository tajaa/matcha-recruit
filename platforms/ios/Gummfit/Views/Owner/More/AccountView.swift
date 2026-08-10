import SwiftUI

/// Billing stays explicitly read-only in iOS; any purchase/portal action belongs
/// to the web handoff to avoid App Store IAP conflicts.
struct AccountView: View {
    @Environment(AppState.self) private var appState
    @State private var subscription: CappeSubscription?
    @State private var error: String?
    var body: some View {
        List {
            Section("Account") { Text(appState.account?.email ?? ""); Text(appState.account?.plan.capitalized ?? "").foregroundStyle(.secondary) }
            Section("Plan") {
                if let subscription { Text(subscription.plan_name ?? subscription.plan_code).font(.headline); Text(subscription.status.capitalized).badge(subscription.status); if let end = subscription.current_period_end { Text("Renews \(end)").font(.caption).foregroundStyle(.secondary) }; if !subscription.addons.isEmpty { ForEach(subscription.addons) { Text("\($0.name) × \($0.quantity)") } } }
                else { Text("No active subscription").foregroundStyle(.secondary) }
                Link("Manage on web", destination: URL(string: "\(APIClient.shared.webOrigin)/cappe/billing")!)
            }
            Section { Button("Sign out", role: .destructive) { appState.didLogout() } }
        }.navigationTitle("Account").overlay(alignment: .top) { ErrorBanner(message: error) }.task { do { subscription = try await BillingService.shared.subscription() } catch { self.error = error.localizedDescription } }
    }
}

struct OwnerCollabsView: View { @State private var vm = OffersViewModel(); var body: some View { List(vm.offers) { offer in NavigationLink { OfferDetailView(offerId: offer.id) } label: { VStack(alignment: .leading) { Text(offer.title); Text("@\(offer.creator_handle) · \(offer.status)").font(.caption).foregroundStyle(.secondary) } } }.overlay { if !vm.isLoading && vm.offers.isEmpty { ContentUnavailableView("No collaborations", systemImage: "person.2.badge.plus") } }.navigationTitle("Collabs").task { await vm.load() }.refreshable { await vm.load() } } }
