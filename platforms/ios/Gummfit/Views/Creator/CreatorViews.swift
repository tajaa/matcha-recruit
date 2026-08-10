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
    @State private var vm = CreatorViewModel(); @State private var handle = ""; @State private var displayName = ""
    var body: some View {
        NavigationStack {
            Group {
                if vm.isLoading { ProgressView() }
                else if let p = vm.profile {
                    List {
                        Section { Text(p.display_name).font(.title2.bold()); Text("@\(p.handle)").foregroundStyle(.secondary); Text(p.status.replacingOccurrences(of: "_", with: " ")).badge(p.status) }
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
        }
    }
}

struct CreatorDealsView: View {
    @State private var vm = OffersViewModel()
    var body: some View { NavigationStack { List(vm.offers) { offer in NavigationLink { OfferDetailView(offerId: offer.id) } label: { VStack(alignment: .leading) { Text(offer.title); Text(offer.status).font(.caption).foregroundStyle(.secondary) } } }.overlay { if !vm.isLoading && vm.offers.isEmpty { ContentUnavailableView("No deals yet", systemImage: "star.bubble") } }.navigationTitle("Deals").task { await vm.load() }.refreshable { await vm.load() } } }
}

struct EarningsView: View {
    @State private var vm = CreatorViewModel()
    var body: some View { NavigationStack { List(vm.earnings) { row in HStack { VStack(alignment: .leading) { Text(row.offer_title); Text(row.label).font(.caption).foregroundStyle(.secondary) }; Spacer(); Text(Formatters.cents(row.amount_cents)).bold() } }.overlay { if !vm.isLoading && vm.earnings.isEmpty { ContentUnavailableView("No earnings yet", systemImage: "dollarsign.circle") } }.navigationTitle("Earnings").task { await vm.loadEarnings() }.refreshable { await vm.loadEarnings() } } }
}

struct OfferDetailView: View {
    let offerId: String; @State private var detail: OfferDetail?; @State private var error: String?
    var body: some View { List { if let d = detail { Section { Text(d.title).font(.headline); Text(d.status).badge(d.status) }; Section("Deliverables") { ForEach(d.deliverables) { item in HStack { Text("\(item.type.capitalized) #\(item.idx + 1)"); Spacer(); Text(item.status).font(.caption) } } }; Section("Payments") { ForEach(d.payments) { Text("\($0.label) · \(Formatters.cents($0.amount_cents))") } }; Section("Messages") { ForEach(d.messages) { Text($0.body) } } } }.overlay(alignment: .top) { ErrorBanner(message: error) }.navigationTitle("Deal").task { do { detail = try await CollabService.shared.offer(offerId) } catch { self.error = error.localizedDescription } } }
}
