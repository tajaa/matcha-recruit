import SwiftUI

struct PlacesView: View {
    @State private var vm = PlacesViewModel()
    @State private var messageTarget: MessageTarget?
    @State private var openedThread: DmThread?

    var body: some View {
        List {
            Section {
                TextField("Search for a business…", text: $vm.query)
                    .textInputAutocapitalization(.words)
                    .autocorrectionDisabled()
            }
            .listRowBackground(TU.inkRaised)

            if !vm.dbResults.isEmpty {
                Section("On Tell-Us") {
                    ForEach(vm.dbResults) { place in
                        PlaceResultRow(place: place, vm: vm) { slug in
                            messageTarget = MessageTarget(slug: slug)
                        }
                    }
                }
                .listRowBackground(TU.inkRaised)
            }

            if !vm.suggestions.isEmpty {
                Section("Add a new place") {
                    ForEach(vm.suggestions) { suggestion in
                        SuggestionRow(suggestion: suggestion, vm: vm)
                    }
                }
                .listRowBackground(TU.inkRaised)
            }

            if vm.noMatches {
                Section {
                    EmptyState(icon: "mappin.slash", title: "No matches",
                               hint: "Add it manually below.")
                }
                .listRowBackground(TU.inkRaised)
            }

            if vm.noMatches || vm.showManualForm {
                Section("Add it manually") {
                    TextField("Business name", text: $vm.addName)
                        .textInputAutocapitalization(.words)
                    TextField("City", text: $vm.addCity)
                        .textInputAutocapitalization(.words)
                    TextField("State (optional)", text: $vm.addState)
                        .textInputAutocapitalization(.characters)
                    if let manualError = vm.manualError {
                        Text(manualError).font(.interFootnote).foregroundStyle(.red)
                    }
                    Button {
                        Task { await vm.submitManual() }
                    } label: {
                        if vm.submittingManual {
                            ProgressView()
                        } else {
                            Text("Add place")
                        }
                    }
                    .disabled(vm.submittingManual)
                }
                .listRowBackground(TU.inkRaised)
            }
        }
        .listStyle(.insetGrouped)
        .themedScreen()
        .navigationTitle("Places")
        .navigationDestination(item: $vm.navigateToken) { scanned in
            IntakeLoaderView(token: scanned.token)
        }
        .navigationDestination(item: $vm.navigateToBrandSlug) { slug in
            BrandDetailView(slug: slug)
        }
        .navigationDestination(item: $openedThread) { thread in
            DmThreadView(vm: DmThreadViewModel(thread: thread))
        }
        .sheet(item: $messageTarget) { target in
            CommsComposerSheet(slug: target.slug) { thread in
                openedThread = thread
            }
        }
        .overlay(alignment: .top) {
            ErrorBanner(message: vm.searching ? nil : vm.searchError).padding(.top, 8)
        }
    }
}

private struct MessageTarget: Identifiable {
    let slug: String
    var id: String { slug }
}

private struct PlaceResultRow: View {
    let place: PlaceSearchResult
    let vm: PlacesViewModel
    let onMessage: (String) -> Void

    var body: some View {
        HStack(spacing: 12) {
            AsyncImage(url: place.logo_url.flatMap(URL.init(string:))) { image in
                image.resizable().scaledToFill()
            } placeholder: {
                Color.secondary.opacity(0.15)
            }
            .frame(width: 40, height: 40)
            .clipShape(RoundedRectangle(cornerRadius: 8))

            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 6) {
                    Text(place.name).font(.interBody)
                    if !place.claimed {
                        Text("unclaimed")
                            .font(.interCaption2.bold())
                            .padding(.horizontal, 6).padding(.vertical, 2)
                            .background(TU.surface, in: Capsule())
                    }
                }
                HStack(spacing: 8) {
                    if let city = place.city {
                        Text([city, place.state].compactMap { $0 }.joined(separator: ", "))
                    }
                    if place.review_count > 0 {
                        Label("\(place.review_count)", systemImage: "star.fill")
                    }
                }
                .font(.interCaption)
                .foregroundStyle(TU.textDim)
            }

            Spacer()

            VStack(alignment: .trailing, spacing: 6) {
                if place.claimed {
                    NavigationLink("View board") {
                        BoardFeedView(slug: place.slug, brandName: place.name)
                    }
                }
                if place.messaging_enabled {
                    Button("Message") { onMessage(place.slug) }
                }
                NavigationLink("See reviews") {
                    BrandDetailView(slug: place.slug)
                }
                if !place.claimed, let token = place.intake_token {
                    Button("Leave feedback") { vm.navigateToken = ScannedToken(target: .intake(token)) }
                }
            }
            .font(.interCaption.bold())
            .buttonStyle(.borderless)
        }
    }
}

private struct SuggestionRow: View {
    let suggestion: PlaceSuggestion
    let vm: PlacesViewModel

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(suggestion.name)
                if let secondary = suggestion.secondary_text {
                    Text(secondary).font(.interCaption).foregroundStyle(TU.textDim)
                }
            }
            Spacer()
            if vm.addingPlaceId == suggestion.place_id {
                ProgressView()
            }
        }
        .contentShape(Rectangle())
        .onTapGesture {
            guard vm.addingPlaceId == nil else { return }
            Task { await vm.selectSuggestion(suggestion) }
        }
        .disabled(vm.addingPlaceId != nil)
    }
}
