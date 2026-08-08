import SwiftUI

struct PlacesView: View {
    @State private var vm = PlacesViewModel()

    var body: some View {
        List {
            Section {
                TextField("Search for a business…", text: $vm.query)
                    .textInputAutocapitalization(.words)
                    .autocorrectionDisabled()
            }

            if !vm.dbResults.isEmpty {
                Section("On Tell-Us") {
                    ForEach(vm.dbResults) { place in
                        PlaceResultRow(place: place, vm: vm)
                    }
                }
            }

            if !vm.suggestions.isEmpty {
                Section("Add a new place") {
                    ForEach(vm.suggestions) { suggestion in
                        SuggestionRow(suggestion: suggestion, vm: vm)
                    }
                }
            }

            if vm.noMatches {
                Section {
                    EmptyState(icon: "mappin.slash", title: "No matches",
                               hint: "Add it manually below.")
                }
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
                        Text(manualError).font(.footnote).foregroundStyle(.red)
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
            }
        }
        .navigationTitle("Places")
        .navigationDestination(item: $vm.navigateToken) { scanned in
            IntakeLoaderView(token: scanned.token)
        }
        .overlay(alignment: .top) {
            ErrorBanner(message: vm.searching ? nil : vm.searchError).padding(.top, 8)
        }
    }
}

private struct PlaceResultRow: View {
    let place: PlaceSearchResult
    let vm: PlacesViewModel

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
                    Text(place.name).font(.body)
                    if !place.claimed {
                        Text("unclaimed")
                            .font(.caption2.bold())
                            .padding(.horizontal, 6).padding(.vertical, 2)
                            .background(Color.secondary.opacity(0.15), in: Capsule())
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
                .font(.caption)
                .foregroundStyle(.secondary)
            }

            Spacer()
        }
        .contentShape(Rectangle())
        .onTapGesture {
            if let token = place.intake_token {
                vm.navigateToken = ScannedToken(token: token)
            } else {
                SafeURL.open(URL(string: APIClient.shared.webOrigin + "/tellus/b/\(place.slug)"))
            }
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
                    Text(secondary).font(.caption).foregroundStyle(.secondary)
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
