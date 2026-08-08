import SwiftUI

struct PromptsEditorView: View {
    @Bindable var vm: BrandSettingsViewModel
    @State private var texts: [String] = []

    var body: some View {
        List {
            ForEach(Array(texts.enumerated()), id: \.offset) { index, _ in
                TextField("Prompt \(index + 1)", text: Binding(
                    get: { texts[index] }, set: { texts[index] = $0 }
                ), axis: .vertical)
            }
            .onMove { texts.move(fromOffsets: $0, toOffset: $1) }
            .onDelete { texts.remove(atOffsets: $0) }

            if texts.count < 5 {
                Button("Add prompt") { texts.append("") }
            }

            if let error = vm.error {
                Text(error).foregroundStyle(.red).font(.footnote)
            }
        }
        .navigationTitle("Prompts")
        .toolbar {
            ToolbarItem(placement: .topBarLeading) { EditButton() }
            ToolbarItem(placement: .topBarTrailing) {
                Button("Save") { Task { await vm.savePrompts(texts) } }
            }
        }
        .onAppear { texts = vm.prompts.map { $0.prompt } }
        .onChange(of: vm.savedPrompts) { _, saved in
            if saved { texts = vm.prompts.map { $0.prompt } }
        }
    }
}
