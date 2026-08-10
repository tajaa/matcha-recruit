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
                if let subscription { Text(subscription.plan_name ?? subscription.plan_code ?? "Unknown plan").font(.headline); Text(subscription.status?.capitalized ?? "Unknown status").badge(subscription.status ?? "unknown"); if let end = subscription.current_period_end { Text("Renews \(end)").font(.caption).foregroundStyle(.secondary) }; if !subscription.addons.isEmpty { ForEach(subscription.addons) { Text("\($0.name) × \($0.quantity)") } } }
                else { Text("No active subscription").foregroundStyle(.secondary) }
                Link("Manage on web", destination: URL(string: "\(APIClient.shared.webOrigin)/cappe/billing")!)
            }
            Section { Button("Sign out", role: .destructive) { appState.didLogout() } }
        }.navigationTitle("Account").overlay(alignment: .top) { ErrorBanner(message: error) }.task { do { subscription = try await BillingService.shared.subscription() } catch { self.error = error.localizedDescription } }
    }
}

struct OwnerCollabsView: View { @State private var vm = OffersViewModel(); @State private var creating = false; var body: some View { List(vm.offers) { offer in NavigationLink { OfferDetailView(offerId: offer.id) } label: { VStack(alignment: .leading) { Text(offer.title); Text("@\(offer.creator_handle) · \(offer.status)").font(.caption).foregroundStyle(.secondary) } } }.overlay { if !vm.isLoading && vm.offers.isEmpty { ContentUnavailableView("No collaborations", systemImage: "person.2.badge.plus") } }.navigationTitle("Collabs").toolbar { Button("New offer", systemImage: "plus") { creating = true } }.task { await vm.load() }.refreshable { await vm.load() }.sheet(isPresented: $creating) { OfferComposerSheet { await vm.load() } } } }

private struct OfferComposerSheet: View {
    let reload: () async -> Void; @Environment(\.dismiss) private var dismiss; @State private var creatorId = ""; @State private var selectedHandle = ""; @State private var creators: [PublicCreatorCard] = []; @State private var title = ""; @State private var campaignId = ""; @State private var cents = ""; @State private var type = "post"; @State private var platform = "instagram"; @State private var message = ""; @State private var error: String?
    var body: some View { NavigationStack { Form { ErrorBanner(message: error); if creators.isEmpty { Text("No published creators found") } else { Picker("Creator", selection: $selectedHandle) { Text("Choose creator").tag(""); ForEach(creators) { Text("\($0.display_name) · @\($0.handle)").tag($0.handle) } }.onChange(of: selectedHandle) { _, handle in Task { await resolveCreator(handle) } } }; TextField("Creator profile ID", text: $creatorId).disabled(!creators.isEmpty); TextField("Offer title", text: $title); TextField("Campaign ID (optional)", text: $campaignId); TextField("Compensation (cents)", text: $cents).keyboardType(.numberPad); TextField("Deliverable type", text: $type); TextField("Platform", text: $platform); TextField("Message", text: $message, axis: .vertical) }.navigationTitle("New offer").toolbar { ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }; ToolbarItem(placement: .confirmationAction) { Button("Send") { Task { await save() } }.disabled(creatorId.isEmpty || title.isEmpty || Int(cents) == nil) } }.task { do { creators = try await CreatorService.shared.directory().creators } catch { self.error = error.localizedDescription } } } }
    private func resolveCreator(_ handle: String) async { guard !handle.isEmpty else { return }; do { creatorId = try await CreatorService.shared.publicProfile(handle: handle).id } catch { self.error = error.localizedDescription } }
    private func save() async { guard let amount = Int(cents) else { error = "Enter a valid amount"; return }; let terms = CollabTerms(compensation_cents: amount, payment_schedule: "upfront", deliverables: [TermsDeliverable(type: type, platform: platform, quantity: 1, spec: nil, due_date: nil)], usage_rights: TermsUsageRights(scope: "organic", duration_months: nil, whitelisting: false), exclusivity: nil, revision_rounds: 1, approval_required: true, ftc_disclosure: true, start_date: nil, end_date: nil, notes: nil); do { _ = try await CollabService.shared.createOffer(OfferCreate(creator_profile_id: creatorId, campaign_id: campaignId.isEmpty ? nil : campaignId, title: title, terms: terms, message: message.isEmpty ? nil : message)); await reload(); dismiss() } catch { self.error = error.localizedDescription } }
}
