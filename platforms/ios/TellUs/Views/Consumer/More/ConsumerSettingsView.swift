import SwiftUI

struct ConsumerSettingsView: View {
    @Environment(AppState.self) private var appState
    @State private var vm = ConsumerSettingsViewModel()
    @State private var displayName = ""
    @State private var leaderboardOptIn = false
    @State private var city = ""
    @State private var state = ""
    @State private var zipcode = ""
    @State private var handle = ""
    @State private var visibility: ProfileVisibility = .friends
    @State private var discoverable = true

    var body: some View {
        Form {
            Section("Profile") {
                TextField("Display name", text: $displayName)
                Toggle("Show me on the leaderboard", isOn: $leaderboardOptIn)
                Button("Save profile") {
                    Task { await vm.saveProfile(appState: appState, displayName: displayName, leaderboardOptIn: leaderboardOptIn) }
                }
                if vm.savedProfile { Text("Saved.").font(.interFootnote).foregroundStyle(.green) }
            }
            .listRowBackground(TU.inkRaised)

            Section("Handle") {
                TextField("@handle", text: $handle).textInputAutocapitalization(.never)
                if vm.handleState == .available { Text("Available").foregroundStyle(.green) }
                if vm.handleState == .taken { Text("Taken").foregroundStyle(.red) }
                Button("Check availability") { Task { await vm.checkHandle(handle) } }
                Button("Claim handle") { Task { await vm.claimHandle(appState: appState, handle: handle) } }
            }
            .listRowBackground(TU.inkRaised)

            Section("Privacy") {
                Picker("Profile visibility", selection: $visibility) {
                    ForEach(ProfileVisibility.allCases.filter { $0 != .unknown }, id: \.self) { value in Text(value.rawValue.capitalized).tag(value) }
                }
                Toggle("Let people find me by @handle", isOn: $discoverable)
                Button("Save privacy") { Task { await vm.savePrivacy(appState: appState, visibility: visibility, discoverable: discoverable, leaderboardOptIn: leaderboardOptIn) } }
            }
            .listRowBackground(TU.inkRaised)

            Section("Location") {
                TextField("City", text: $city)
                TextField("State", text: $state)
                TextField("Zip code", text: $zipcode)
                Button("Save location") {
                    Task { await vm.saveLocation(appState: appState, city: city, state: state, zipcode: zipcode) }
                }
                if vm.savedLocation { Text("Saved.").font(.interFootnote).foregroundStyle(.green) }
            }
            .listRowBackground(TU.inkRaised)

            if let error = vm.error {
                Section { Text(error).foregroundStyle(.red).font(.interFootnote) }
                    .listRowBackground(TU.inkRaised)
            }
        }
        .themedScreen()
        .navigationTitle("Settings")
        .onAppear {
            displayName = appState.account?.display_name ?? ""
            leaderboardOptIn = appState.account?.leaderboard_opt_in ?? false
            handle = appState.account?.handle ?? ""
            visibility = ProfileVisibility(rawValue: appState.account?.profile_visibility ?? "friends") ?? .friends
            discoverable = appState.account?.discoverable ?? true
            city = appState.account?.city ?? ""
            state = appState.account?.state ?? ""
        }
    }
}
