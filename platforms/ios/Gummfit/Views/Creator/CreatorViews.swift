import SwiftUI
import Observation

@MainActor @Observable final class CreatorViewModel: LoadableVM {
    var profile: CreatorProfileMe?; var earnings: [EarningsRow] = []; var isLoading = false; var error: String?
    func loadProfile() async { await withLoad { profile = try await CreatorService.shared.me() } }
    func loadEarnings() async { await withLoad { earnings = try await CreatorService.shared.earnings() } }
    func submit() async { do { profile = try await CreatorService.shared.submit() } catch { self.error = error.localizedDescription } }
}
@MainActor @Observable final class OffersViewModel: LoadableVM { var offers: [OfferListItem] = []; var isLoading = false; var error: String?; func load() async { await withLoad { offers = try await CollabService.shared.offers().offers } } }

struct CreatorProfileView: View {
    @State private var vm = CreatorViewModel(); @State private var handle = ""; @State private var displayName = ""; @State private var editing = false
    var body: some View {
        NavigationStack {
            Group {
                if vm.isLoading { ProgressView() }
                else if let p = vm.profile {
                    List {
                        Section { Text(p.display_name).font(.title2.bold()); Text("@\(p.handle)").foregroundStyle(.secondary); Text(p.status.replacingOccurrences(of: "_", with: " ")).badge(p.status); Button("Edit profile") { editing = true } }
                        if let bio = p.bio { Section("About") { Text(bio) } }
                        Section("Portfolio") { ForEach(p.portfolio) { Text($0.title) } }
                        Section("Rates") { ForEach(p.rates) { Text("\($0.deliverable_type.capitalized) · \(Formatters.cents($0.price_cents))") } }
                        if p.status == "draft" || p.status == "rejected" { Button("Submit for review") { Task { await vm.submit() } } }
                    }
                } else {
                    Form { TextField("Handle", text: $handle); TextField("Display name", text: $displayName); Button("Create profile") { Task { do { _ = try await CreatorService.shared.create(CreatorProfileCreate(handle: handle, display_name: displayName)); await vm.loadProfile() } catch { vm.error = error.localizedDescription } } }.disabled(handle.isEmpty || displayName.isEmpty) }
                }
            }
            .overlay(alignment: .top) { ErrorBanner(message: vm.error) }
            .navigationTitle("Profile").task { await vm.loadProfile() }.refreshable { await vm.loadProfile() }
            .sheet(isPresented: $editing) { if let profile = vm.profile { CreatorProfileEditSheet(profile: profile) { await vm.loadProfile() } } }
        }
    }
}

private struct CreatorProfileEditSheet: View {
    let profile: CreatorProfileMe; let reload: () async -> Void; @Environment(\.dismiss) private var dismiss
    @State private var name: String; @State private var bio: String; @State private var location: String; @State private var niches: String; @State private var languages: String; @State private var openToOffers: Bool; @State private var error: String?
    init(profile: CreatorProfileMe, reload: @escaping () async -> Void) { self.profile = profile; self.reload = reload; _name = State(initialValue: profile.display_name); _bio = State(initialValue: profile.bio ?? ""); _location = State(initialValue: profile.location ?? ""); _niches = State(initialValue: profile.niches.joined(separator: ", ")); _languages = State(initialValue: profile.languages.joined(separator: ", ")); _openToOffers = State(initialValue: profile.open_to_offers) }
    var body: some View { NavigationStack { Form { ErrorBanner(message: error); TextField("Display name", text: $name); TextField("Bio", text: $bio, axis: .vertical); TextField("Location", text: $location); TextField("Niches (comma-separated)", text: $niches); TextField("Languages (comma-separated)", text: $languages); Toggle("Open to offers", isOn: $openToOffers) }.navigationTitle("Edit profile").toolbar { ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }; ToolbarItem(placement: .confirmationAction) { Button("Save") { Task { await save() } }.disabled(name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty) } } } }
    private func save() async { do { _ = try await CreatorService.shared.update(CreatorProfileUpdate(display_name: name, avatar_url: nil, cover_url: nil, bio: bio.isEmpty ? nil : bio, location: location.isEmpty ? nil : location, niches: niches.csv, languages: languages.csv, open_to_offers: openToOffers)); await reload(); dismiss() } catch { self.error = error.localizedDescription } }
}
private extension String { var csv: [String] { split(separator: ",").map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }.filter { !$0.isEmpty } } }

struct CreatorDealsView: View {
    @State private var vm = OffersViewModel()
    var body: some View { NavigationStack { List(vm.offers) { offer in NavigationLink { OfferDetailView(offerId: offer.id) } label: { VStack(alignment: .leading) { Text(offer.title); Text(offer.status).font(.caption).foregroundStyle(.secondary) } } }.overlay { if !vm.isLoading && vm.offers.isEmpty { ContentUnavailableView("No deals yet", systemImage: "star.bubble") } }.navigationTitle("Deals").task { await vm.load() }.refreshable { await vm.load() } } }
}

struct EarningsView: View {
    @State private var vm = CreatorViewModel()
    var body: some View { NavigationStack { List(vm.earnings) { row in HStack { VStack(alignment: .leading) { Text(row.offer_title); Text(row.label).font(.caption).foregroundStyle(.secondary) }; Spacer(); Text(Formatters.cents(row.amount_cents)).bold() } }.overlay { if !vm.isLoading && vm.earnings.isEmpty { ContentUnavailableView("No earnings yet", systemImage: "dollarsign.circle") } }.navigationTitle("Earnings").task { await vm.loadEarnings() }.refreshable { await vm.loadEarnings() } } }
}

struct OfferDetailView: View {
    let offerId: String; @State private var detail: OfferDetail?; @State private var error: String?; @State private var message = ""; @State private var cancelReason = ""; @State private var showCancel = false; @State private var submitting: Deliverable?
    var body: some View { List { if let d = detail { Section { Text(d.title).font(.headline); Text(d.status).badge(d.status); if let cents = d.total_cents { Text(Formatters.cents(cents)) } }; actionSection(d); Section("Deliverables") { ForEach(d.deliverables) { item in HStack { Text("\(item.type.capitalized) #\(item.idx + 1)"); Spacer(); Text(item.status).font(.caption) }.swipeActions { if d.side == "creator" && ["pending", "revision_requested"].contains(item.status) { Button("Submit") { submitting = item } }; if d.side == "brand" && item.status == "submitted" { Button("Approve") { Task { await perform { try await CollabService.shared.approve(offerId, deliverableId: item.id) } } } } } } }; Section("Payments") { ForEach(d.payments) { Text("\($0.label) · \(Formatters.cents($0.amount_cents))") } }; Section("Messages") { ForEach(d.messages) { message in VStack(alignment: .leading) { Text(message.sender.capitalized).font(.caption.bold()); Text(message.body) } }; HStack { TextField("Message", text: $message); Button("Send") { Task { await sendMessage() } }.disabled(message.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty) } } } }.overlay(alignment: .top) { ErrorBanner(message: error) }.navigationTitle("Deal").task { await load() }.refreshable { await load() }.alert("Cancel deal", isPresented: $showCancel) { TextField("Reason", text: $cancelReason); Button("Cancel deal", role: .destructive) { Task { await perform { try await CollabService.shared.cancel(offerId, reason: cancelReason) } } }; Button("Keep deal", role: .cancel) {} }.sheet(item: $submitting) { item in DeliverableSubmitSheet(deliverable: item) { body in do { _ = try await CollabService.shared.submit(offerId, deliverableId: item.id, body: body); await load() } catch { error = error.localizedDescription } } } }
    @ViewBuilder private func actionSection(_ d: OfferDetail) -> some View { if ["sent", "negotiating"].contains(d.status) { Section("Offer") { if d.side == "creator" { Button("Accept") { Task { await perform { try await CollabService.shared.accept(offerId) } } }; Button("Decline", role: .destructive) { Task { await perform { try await CollabService.shared.decline(offerId, reason: nil) } } } } else { Button("Withdraw", role: .destructive) { Task { await perform { try await CollabService.shared.withdraw(offerId) } } } } } } else if ["accepted", "active"].contains(d.status) { Section { Button("Cancel deal", role: .destructive) { showCancel = true } } } }
    private func load() async { do { detail = try await CollabService.shared.offer(offerId) } catch { self.error = error.localizedDescription } }
    private func sendMessage() async { do { _ = try await CollabService.shared.message(offerId, message); message = ""; await load() } catch { self.error = error.localizedDescription } }
    private func perform(_ action: () async throws -> OfferDetail) async { do { detail = try await action() } catch { self.error = error.localizedDescription } }
}
private struct DeliverableSubmitSheet: View { let deliverable: Deliverable; let submit: (DeliverableSubmit) async -> Void; @Environment(\.dismiss) private var dismiss; @State private var url = ""; @State private var note = ""; var body: some View { NavigationStack { Form { TextField("Submission URL", text: $url).textInputAutocapitalization(.never); TextField("Note", text: $note, axis: .vertical) }.navigationTitle("Submit \(deliverable.type)").toolbar { ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }; ToolbarItem(placement: .confirmationAction) { Button("Submit") { Task { await submit(DeliverableSubmit(submission_url: url, submission_note: note.isEmpty ? nil : note, proof_media_url: nil)); dismiss() } }.disabled(url.count < 8) } } } }
