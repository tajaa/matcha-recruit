import SwiftUI
import Observation
import PhotosUI

@MainActor @Observable final class CreatorViewModel: LoadableVM {
    var profile: CreatorProfileMe?; var earnings: [EarningsRow] = []; var isLoading = false; var error: String?
    func loadProfile() async { await withLoad { profile = try await CreatorService.shared.me() } }
    func loadEarnings() async { await withLoad { earnings = try await CreatorService.shared.earnings() } }
    func submit() async { do { profile = try await CreatorService.shared.submit() } catch { self.error = error.localizedDescription } }
}
@MainActor @Observable final class OffersViewModel: LoadableVM { var offers: [OfferListItem] = []; var isLoading = false; var error: String?; func load() async { await withLoad { offers = try await CollabService.shared.offers().offers } } }

struct CreatorProfileView: View {
    @State private var vm = CreatorViewModel(); @State private var handle = ""; @State private var displayName = ""; @State private var editing = false; @State private var editor: CreatorCollection?; @State private var avatarPicker: PhotosPickerItem?; @State private var coverPicker: PhotosPickerItem?
    var body: some View {
        NavigationStack {
            Group {
                if vm.isLoading { ProgressView() }
                else if let p = vm.profile {
                    List {
                        Section { Text(p.display_name).font(.title2.bold()); Text("@\(p.handle)").foregroundStyle(.secondary); Text(p.status.replacingOccurrences(of: "_", with: " ")).badge(p.status); HStack { PhotosPicker(selection: $avatarPicker, matching: .images) { Label("Avatar", systemImage: "person.crop.circle") }; PhotosPicker(selection: $coverPicker, matching: .images) { Label("Cover", systemImage: "photo") } }; Button("Edit profile") { editing = true } }
                        if let bio = p.bio { Section("About") { Text(bio) } }
                        Section("Socials") { ForEach(p.socials) { social in Text("\(social.platform.capitalized) · @\(social.handle)").swipeActions { Button("Delete", role: .destructive) { Task { await deleteSocial(social, profile: p) } } } }; Button("Add social", systemImage: "plus") { editor = .socials } }
                        Section("Portfolio") { ForEach(p.portfolio) { item in Text(item.title).swipeActions { Button("Delete", role: .destructive) { Task { await deletePortfolio(item, profile: p) } } } }; Button("Add portfolio item", systemImage: "plus") { editor = .portfolio } }
                        Section("Rates") { ForEach(p.rates) { rate in Text("\(rate.deliverable_type.capitalized) · \(Formatters.cents(rate.price_cents))").swipeActions { Button("Delete", role: .destructive) { Task { await deleteRate(rate, profile: p) } } } }; Button("Add rate", systemImage: "plus") { editor = .rates } }
                        if p.status == "draft" || p.status == "rejected" { Button("Submit for review") { Task { await vm.submit() } } }
                    }
                } else {
                    Form { TextField("Handle", text: $handle); TextField("Display name", text: $displayName); Button("Create profile") { Task { do { _ = try await CreatorService.shared.create(CreatorProfileCreate(handle: handle, display_name: displayName)); await vm.loadProfile() } catch { vm.error = error.localizedDescription } } }.disabled(handle.isEmpty || displayName.isEmpty) }
                }
            }
            .overlay(alignment: .top) { ErrorBanner(message: vm.error) }
            .navigationTitle("Profile").task { await vm.loadProfile() }.refreshable { await vm.loadProfile() }
            .sheet(isPresented: $editing) { if let profile = vm.profile { CreatorProfileEditSheet(profile: profile) { await vm.loadProfile() } } }
            .sheet(item: $editor) { collection in if let profile = vm.profile { CreatorCollectionSheet(collection: collection, profile: profile) { await vm.loadProfile() } } }
            .onChange(of: avatarPicker) { _, item in Task { await upload(item, cover: false) } }
            .onChange(of: coverPicker) { _, item in Task { await upload(item, cover: true) } }
        }
    }
    private func upload(_ item: PhotosPickerItem?, cover: Bool) async { guard let item, let data = try? await item.loadTransferable(type: Data.self) else { return }; do { let prepared = try ImagePrep.prepare(data: data, mimeType: "image/jpeg", filename: cover ? "cover.jpg" : "avatar.jpg"); let result = try await UploadService.shared.uploadCreatorMedia(prepared: prepared); let p = vm.profile; _ = try await CreatorService.shared.update(CreatorProfileUpdate(display_name: nil, avatar_url: cover ? nil : result.url, cover_url: cover ? result.url : nil, bio: nil, location: nil, niches: nil, languages: nil, open_to_offers: nil)); await vm.loadProfile() } catch { vm.error = error.localizedDescription } }
    private func deleteSocial(_ item: CreatorSocial, profile: CreatorProfileMe) async { do { _ = try await CreatorService.shared.replaceSocials(profile.socials.filter { $0.id != item.id }.map { CreatorSocialInput(platform: $0.platform, handle: $0.handle, url: $0.url, follower_count: $0.follower_count, engagement_rate: $0.engagement_rate, sort_order: $0.sort_order) }); await vm.loadProfile() } catch { vm.error = error.localizedDescription } }
    private func deletePortfolio(_ item: CreatorPortfolioItem, profile: CreatorProfileMe) async { do { _ = try await CreatorService.shared.replacePortfolio(profile.portfolio.filter { $0.id != item.id }.map { CreatorPortfolioInput(title: $0.title, description: $0.description, media_url: $0.media_url, media_type: $0.media_type, external_url: $0.external_url, brand_name: $0.brand_name, metrics: $0.metrics, sort_order: $0.sort_order) }); await vm.loadProfile() } catch { vm.error = error.localizedDescription } }
    private func deleteRate(_ item: CreatorRate, profile: CreatorProfileMe) async { do { _ = try await CreatorService.shared.replaceRates(profile.rates.filter { $0.id != item.id }.map { CreatorRateInput(deliverable_type: $0.deliverable_type, platform: $0.platform, price_cents: $0.price_cents, negotiable: $0.negotiable, notes: $0.notes, sort_order: $0.sort_order) }); await vm.loadProfile() } catch { vm.error = error.localizedDescription } }
}
private enum CreatorCollection: String, Identifiable { case socials, portfolio, rates; var id: String { rawValue } }
private struct CreatorCollectionSheet: View {
    let collection: CreatorCollection; let profile: CreatorProfileMe; let reload: () async -> Void; @Environment(\.dismiss) private var dismiss; @State private var first = ""; @State private var second = ""; @State private var third = ""; @State private var mediaPicker: PhotosPickerItem?; @State private var error: String?
    var body: some View {
        NavigationStack {
            Form {
                ErrorBanner(message: error)
                switch collection {
                case .socials:
                    TextField("Platform", text: $first)
                    TextField("Handle", text: $second)
                    TextField("https:// URL", text: $third).textInputAutocapitalization(.never)
                case .portfolio:
                    TextField("Title", text: $first)
                    TextField("Description", text: $second, axis: .vertical)
                    TextField("External URL", text: $third).textInputAutocapitalization(.never)
                    PhotosPicker(selection: $mediaPicker, matching: .images) { Label("Choose media", systemImage: "photo") }
                case .rates:
                    TextField("Deliverable type", text: $first)
                    TextField("Platform", text: $second)
                    TextField("Price in cents", text: $third).keyboardType(.numberPad)
                }
            }
            .navigationTitle("Add \(collection.rawValue.dropLast())")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) { Button("Save") { Task { await save() } }.disabled(first.isEmpty || second.isEmpty || third.isEmpty) }
            }
        }
    }
    private func save() async { do { switch collection { case .socials: let inputs = profile.socials.map { CreatorSocialInput(platform: $0.platform, handle: $0.handle, url: $0.url, follower_count: $0.follower_count, engagement_rate: $0.engagement_rate, sort_order: $0.sort_order) } + [CreatorSocialInput(platform: first, handle: second, url: third, follower_count: nil, engagement_rate: nil, sort_order: profile.socials.count)]; _ = try await CreatorService.shared.replaceSocials(inputs); case .portfolio: var mediaURL: String?; if let item = mediaPicker, let data = try? await item.loadTransferable(type: Data.self) { let prepared = try ImagePrep.prepare(data: data, mimeType: "image/jpeg", filename: "portfolio.jpg"); mediaURL = try await UploadService.shared.uploadCreatorMedia(prepared: prepared).url }; let inputs = profile.portfolio.map { CreatorPortfolioInput(title: $0.title, description: $0.description, media_url: $0.media_url, media_type: $0.media_type, external_url: $0.external_url, brand_name: $0.brand_name, metrics: $0.metrics, sort_order: $0.sort_order) } + [CreatorPortfolioInput(title: first, description: second.isEmpty ? nil : second, media_url: mediaURL, media_type: mediaURL == nil ? nil : "image", external_url: third.isEmpty ? nil : third, brand_name: nil, metrics: [:], sort_order: profile.portfolio.count)]; _ = try await CreatorService.shared.replacePortfolio(inputs); case .rates: guard let cents = Int(third) else { error = "Price must be a whole number of cents"; return }; let inputs = profile.rates.map { CreatorRateInput(deliverable_type: $0.deliverable_type, platform: $0.platform, price_cents: $0.price_cents, negotiable: $0.negotiable, notes: $0.notes, sort_order: $0.sort_order) } + [CreatorRateInput(deliverable_type: first, platform: second, price_cents: cents, negotiable: true, notes: nil, sort_order: profile.rates.count)]; _ = try await CreatorService.shared.replaceRates(inputs) }; await reload(); dismiss() } catch { self.error = error.localizedDescription } }
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
    let offerId: String; @State private var detail: OfferDetail?; @State private var error: String?; @State private var message = ""; @State private var cancelReason = ""; @State private var showCancel = false; @State private var submitting: Deliverable?; @State private var reviewing: Deliverable?; @State private var showCounter = false
    var body: some View { List { if let d = detail { Section { Text(d.title).font(.headline); Text(d.status).badge(d.status); if let cents = d.total_cents { Text(Formatters.cents(cents)) } }; actionSection(d); Section("Deliverables") { ForEach(d.deliverables) { item in HStack { Text("\(item.type.capitalized) #\(item.idx + 1)"); Spacer(); Text(item.status).font(.caption) }.swipeActions { if d.side == "creator" && ["pending", "revision_requested"].contains(item.status) { Button("Submit") { submitting = item } }; if d.side == "brand" && item.status == "submitted" { Button("Revise") { reviewing = item }; Button("Approve") { Task { await perform { try await CollabService.shared.approve(offerId, deliverableId: item.id) } } } } } } }; Section("Payments") { ForEach(d.payments) { payment in HStack { Text("\(payment.label) · \(Formatters.cents(payment.amount_cents))"); Spacer(); if d.side == "brand" && ["due", "processing"].contains(payment.status) { Link("Pay on web", destination: URL(string: "\(APIClient.shared.webOrigin)/collabs/\(offerId)/payments/\(payment.id)")!) } else if d.side == "creator" && ["due", "processing"].contains(payment.status) { Button("Nudge") { Task { try? await CollabService.shared.nudgePayment(offerId, paymentId: payment.id) } } } } } }; Section("Messages") { ForEach(d.messages) { message in VStack(alignment: .leading) { Text(message.sender.capitalized).font(.caption.bold()); Text(message.body) } }; HStack { TextField("Message", text: $message); Button("Send") { Task { await sendMessage() } }.disabled(message.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty) } } } }.overlay(alignment: .top) { ErrorBanner(message: error) }.navigationTitle("Deal").task { await load() }.refreshable { await load() }.alert("Cancel deal", isPresented: $showCancel) { TextField("Reason", text: $cancelReason); Button("Cancel deal", role: .destructive) { Task { await perform { try await CollabService.shared.cancel(offerId, reason: cancelReason) } } }; Button("Keep deal", role: .cancel) {} }.sheet(item: $submitting) { item in DeliverableSubmitSheet(deliverable: item) { body in _ = try await CollabService.shared.submit(offerId, deliverableId: item.id, body: body); await load() } }.sheet(isPresented: $showCounter) { CounterOfferSheet { terms, note in await perform { try await CollabService.shared.counter(offerId, terms: terms, message: note) } } }.alert("Request revision", isPresented: Binding(get: { reviewing != nil }, set: { if !$0 { reviewing = nil } })) { TextField("Review note", text: $message); Button("Request revision") { if let reviewing { Task { await perform { try await CollabService.shared.requestRevision(offerId, deliverableId: reviewing.id, note: message) }; message = "" } } }; Button("Cancel", role: .cancel) {} } }
    @ViewBuilder private func actionSection(_ d: OfferDetail) -> some View { if ["sent", "negotiating"].contains(d.status) { Section("Offer") { Button("Counter offer") { showCounter = true }; if d.side == "creator" { Button("Accept") { Task { await perform { try await CollabService.shared.accept(offerId) } } }; Button("Decline", role: .destructive) { Task { await perform { try await CollabService.shared.decline(offerId, reason: nil) } } } } else { Button("Withdraw", role: .destructive) { Task { await perform { try await CollabService.shared.withdraw(offerId) } } } } } } else if ["accepted", "active"].contains(d.status) { Section { Button("Cancel deal", role: .destructive) { showCancel = true } } } }
    private func load() async { do { detail = try await CollabService.shared.offer(offerId) } catch { self.error = error.localizedDescription } }
    private func sendMessage() async { do { _ = try await CollabService.shared.message(offerId, message); message = ""; await load() } catch { self.error = error.localizedDescription } }
    private func perform(_ action: () async throws -> OfferDetail) async { do { detail = try await action() } catch { self.error = error.localizedDescription } }
}
private struct DeliverableSubmitSheet: View {
    let deliverable: Deliverable
    let submit: (DeliverableSubmit) async throws -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var url = ""
    @State private var note = ""
    @State private var proofPicker: PhotosPickerItem?
    @State private var error: String?
    var body: some View {
        NavigationStack {
            Form {
                ErrorBanner(message: error)
                TextField("Submission URL", text: $url).textInputAutocapitalization(.never)
                TextField("Note", text: $note, axis: .vertical)
                PhotosPicker(selection: $proofPicker, matching: .any(of: [.images, .videos])) { Label("Attach proof media", systemImage: "paperclip") }
            }
            .navigationTitle("Submit \(deliverable.type)")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Submit") {
                        Task {
                            if await submitBody() { dismiss() }
                        }
                    }.disabled(url.count < 8)
                }
            }
        }
    }
    private func submitBody() async -> Bool {
        var proofURL: String?
        if let picker = proofPicker {
            guard let data = try? await picker.loadTransferable(type: Data.self) else {
                error = "Could not read the selected proof file."
                return false
            }
            do {
                let mime = picker.supportedContentTypes.first?.preferredMIMEType ?? "image/jpeg"
                if mime.hasPrefix("image/") {
                    let prepared = try ImagePrep.prepare(data: data, mimeType: mime, filename: "proof.jpg")
                    proofURL = try await UploadService.shared.uploadCreatorMedia(prepared: prepared).url
                } else {
                    proofURL = try await UploadService.shared.uploadCreatorFile(data: data, mimeType: mime, filename: "proof.mov").url
                }
            } catch {
                self.error = error.localizedDescription
                return false
            }
        }
        do {
            try await submit(DeliverableSubmit(submission_url: url, submission_note: note.isEmpty ? nil : note, proof_media_url: proofURL))
            return true
        } catch {
            self.error = error.localizedDescription
            return false
        }
    }
}

private struct CounterOfferSheet: View {
    let submit: (CollabTerms, String?) async -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var compensation = ""
    @State private var type = "post"
    @State private var platform = "instagram"
    @State private var schedule = "upfront"
    @State private var quantity = "1"
    @State private var spec = ""
    @State private var usageScope = "organic"
    @State private var usageMonths = ""
    @State private var exclusivityCategory = ""
    @State private var exclusivityMonths = ""
    @State private var revisions = "1"
    @State private var note = ""
    @State private var error: String?
    var body: some View {
        NavigationStack {
            Form {
                ErrorBanner(message: error)
                TextField("Compensation (cents)", text: $compensation).keyboardType(.numberPad)
                TextField("Deliverable type", text: $type)
                TextField("Platform", text: $platform)
                Picker("Payment schedule", selection: $schedule) { Text("Upfront").tag("upfront"); Text("50 / 50").tag("split_50_50"); Text("Per deliverable").tag("per_deliverable") }
                TextField("Quantity", text: $quantity).keyboardType(.numberPad)
                TextField("Deliverable spec", text: $spec, axis: .vertical)
                Picker("Usage rights", selection: $usageScope) { Text("Organic").tag("organic"); Text("Paid").tag("paid") }
                TextField("Usage duration (months)", text: $usageMonths).keyboardType(.numberPad)
                TextField("Exclusivity category (optional)", text: $exclusivityCategory)
                TextField("Exclusivity months", text: $exclusivityMonths).keyboardType(.numberPad)
                TextField("Revision rounds", text: $revisions).keyboardType(.numberPad)
                TextField("Message", text: $note, axis: .vertical)
            }
            .navigationTitle("Counter offer")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) { Button("Send") { Task { await save() } }.disabled(Int(compensation) == nil) }
            }
        }
    }
    private func save() async {
        guard let cents = Int(compensation), cents >= 0 else { error = "Enter a valid amount"; return }
        let deliverable = TermsDeliverable(type: type, platform: platform, quantity: max(1, Int(quantity) ?? 1), spec: spec.isEmpty ? nil : spec, due_date: nil)
        let exclusivity = exclusivityCategory.isEmpty ? nil : TermsExclusivity(category: exclusivityCategory, duration_months: max(1, Int(exclusivityMonths) ?? 1))
        let terms = CollabTerms(compensation_cents: cents, payment_schedule: schedule, deliverables: [deliverable], usage_rights: TermsUsageRights(scope: usageScope, duration_months: Int(usageMonths), whitelisting: false), exclusivity: exclusivity, revision_rounds: max(0, Int(revisions) ?? 1), approval_required: true, ftc_disclosure: true, start_date: nil, end_date: nil, notes: note.isEmpty ? nil : note)
        await submit(terms, note.isEmpty ? nil : note)
        dismiss()
    }
}
