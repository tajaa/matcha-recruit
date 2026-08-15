import PhotosUI
import SwiftUI

struct BrandSettingsView: View {
    @State private var vm = BrandSettingsViewModel()
    @State private var name = ""
    @State private var rewardMode: RewardMode = .auto
    @State private var messagingEnabled = false
    @State private var logoItem: PhotosPickerItem?

    var body: some View {
        Form {
            identitySection
            promptsSection
            errorSection
        }
        .navigationTitle("Settings")
        .task { await vm.load() }
        .onChange(of: vm.brand?.name) { _, newName in name = newName ?? name }
        .onChange(of: vm.brand?.reward_mode) { _, newMode in if let newMode { rewardMode = newMode } }
        .onChange(of: vm.brand?.messaging_enabled) { _, enabled in messagingEnabled = enabled ?? false }
        .onChange(of: logoItem) { _, item in
            guard let item else { return }
            Task { await vm.uploadLogo(item: item); logoItem = nil }
        }
    }

    private var identitySection: some View {
        Section("Identity") {
            logoPreview
            PhotosPicker("Change logo", selection: $logoItem, matching: .images)
            removeLogoButton
            TextField("Brand name", text: $name)
            rewardModePicker
            Toggle("Allow customer messages", isOn: Binding(
                get: { messagingEnabled },
                set: { newValue in
                    messagingEnabled = newValue
                    Task { await vm.setMessagingEnabled(newValue) }
                }
            ))
            Text("Customers can ask questions from your TellUs profile when this is on.")
                .font(.interFootnote).foregroundStyle(.secondary)
            Button("Save") { Task { await vm.saveBrand(name: name, rewardMode: rewardMode) } }
            if vm.savedBrand { Text("Saved.").font(.interFootnote).foregroundStyle(.green) }
        }
    }

    @ViewBuilder
    private var removeLogoButton: some View {
        if vm.brand?.logo_url != nil {
            Button("Remove logo", role: .destructive) { Task { await vm.removeLogo() } }
        }
    }

    private var rewardModePicker: some View {
        Picker("Reward mode", selection: $rewardMode) {
            Text("Auto — credit points instantly").tag(RewardMode.auto)
            Text("Manual — approve each submission").tag(RewardMode.manual)
        }
    }

    private var promptsSection: some View {
        Section("Intake prompts") {
            NavigationLink("Edit prompts (\(vm.prompts.count)/5)") { PromptsEditorView(vm: vm) }
        }
    }

    @ViewBuilder
    private var errorSection: some View {
        if let error = vm.error {
            Section { Text(error).foregroundStyle(.red).font(.interFootnote) }
        }
    }

    @ViewBuilder
    private var logoPreview: some View {
        if let logoURL = vm.brand?.logo_url, let url = URL(string: logoURL) {
            AsyncImage(url: url) { image in
                image.resizable().scaledToFit()
            } placeholder: {
                ProgressView()
            }
            .frame(width: 80, height: 80)
            .clipShape(RoundedRectangle(cornerRadius: 12))
        }
    }
}
