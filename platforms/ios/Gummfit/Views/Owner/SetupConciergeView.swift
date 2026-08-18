import SwiftUI

struct SetupConciergeView: View {
    let site: CappeSite
    @State private var vm: SetupMerlinViewModel

    init(site: CappeSite) {
        self.site = site
        _vm = State(initialValue: SetupMerlinViewModel(siteId: site.id))
    }

    var body: some View {
        VStack(spacing: 0) {
            ErrorBanner(message: vm.error)
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 12) {
                    Text("Tell Merlin what you want to set up. It will propose changes for your approval before writing anything.")
                        .font(.subheadline).foregroundStyle(GummfitTheme.textDim)
                    ForEach(vm.stagedActions) { action in actionCard(action) }
                    ForEach(vm.messages) { message in
                        Text(message.content)
                            .font(.subheadline)
                            .foregroundStyle(message.role == "user" ? GummfitTheme.background : GummfitTheme.textPrimary)
                            .padding(12)
                            .background(message.role == "user" ? GummfitTheme.accent : GummfitTheme.surface, in: RoundedRectangle(cornerRadius: 14))
                            .frame(maxWidth: .infinity, alignment: message.role == "user" ? .trailing : .leading)
                    }
                    if !vm.readiness.isEmpty {
                        readinessCard
                    }
                }
                .padding()
            }
            HStack(alignment: .bottom, spacing: 8) {
                TextField("e.g. add a contact page", text: $vm.draft, axis: .vertical)
                    .textFieldStyle(.roundedBorder)
                Button { Task { await vm.send() } } label: { Image(systemName: "arrow.up.circle.fill").font(.title2) }
                    .foregroundStyle(GummfitTheme.accent)
                    .disabled(vm.draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || vm.isLoading)
            }
            .padding()
            .background(GummfitTheme.surface)
        }
        .navigationTitle("Set up your site")
        .gummfitScreenChrome()
        .task { await vm.load() }
    }

    private func actionCard(_ action: CappeSetupActionEntry) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Label(action.summary, systemImage: action.status == "proposed" ? "checklist" : "checkmark.circle.fill")
                .font(.subheadline.weight(.semibold))
            if let message = action.message { Text(message).font(.caption).foregroundStyle(GummfitTheme.textDim) }
            if action.status == "proposed" {
                HStack {
                    Button("Do it") { Task { await vm.execute(action) } }.buttonStyle(.gummfitPrimary).controlSize(.small)
                    Button("Dismiss") { Task { await vm.dismiss(action) } }.buttonStyle(.gummfitSecondary).controlSize(.small)
                }
            }
        }
        .gummfitCard()
    }

    private var readinessCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Setup progress").font(.headline)
            ForEach(vm.readiness.keys.sorted(), id: \.self) { key in
                HStack { Image(systemName: "checkmark.circle").foregroundStyle(GummfitTheme.accent); Text(key.capitalized).font(.caption) } }
        }
        .gummfitCard()
    }
}
