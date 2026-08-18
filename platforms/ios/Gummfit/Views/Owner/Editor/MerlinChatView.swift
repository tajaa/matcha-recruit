import SwiftUI

struct MerlinChatView: View {
    @State private var vm: MerlinChatViewModel
    @Environment(\.dismiss) private var dismiss

    init(editor: PageEditorViewModel) { _vm = State(initialValue: MerlinChatViewModel(editor: editor)) }

    var body: some View {
        VStack(spacing: 0) {
            ErrorBanner(message: vm.error)
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 12) {
                    if vm.messages.isEmpty && vm.liveSteps.isEmpty {
                        Text("Ask Merlin to change your page. Try: “Add a pricing section and make the theme dark.”")
                            .font(.subheadline).foregroundStyle(GummfitTheme.textDim).padding()
                    }
                    ForEach(vm.messages) { message in
                        Text(message.content)
                            .font(.subheadline)
                            .foregroundStyle(message.role == "user" ? GummfitTheme.background : GummfitTheme.textPrimary)
                            .padding(12)
                            .background(message.role == "user" ? GummfitTheme.accent : GummfitTheme.surface, in: RoundedRectangle(cornerRadius: 14))
                            .frame(maxWidth: .infinity, alignment: message.role == "user" ? .trailing : .leading)
                    }
                    ForEach(vm.liveSteps) { step in
                        Label(step.label, systemImage: "sparkles").font(.caption).foregroundStyle(GummfitTheme.textDim)
                    }
                }
                .padding()
            }
            HStack(alignment: .bottom, spacing: 8) {
                TextField("Ask Merlin…", text: $vm.draft, axis: .vertical)
                    .textFieldStyle(.roundedBorder)
                    .lineLimit(1...5)
                Button {
                    if vm.isLoading { vm.cancel() } else { Task { await vm.send() } }
                } label: { Image(systemName: vm.isLoading ? "stop.fill" : "arrow.up.circle.fill").font(.title2) }
                    .foregroundStyle(GummfitTheme.accent)
                    .disabled(vm.draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && !vm.isLoading)
            }
            .padding()
            .background(GummfitTheme.surface)
        }
        .navigationTitle("Merlin")
        .toolbar { ToolbarItem(placement: .topBarLeading) { Button("Done") { dismiss() } } }
        .task { await vm.load() }
        .gummfitScreenChrome()
    }
}
