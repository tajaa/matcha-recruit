import SwiftUI

struct DesignInspectorView: View {
    @Bindable var vm: PageEditorViewModel
    let blockKey: String

    var body: some View {
        if let schema = vm.schema, !schema.design.isEmpty {
            VStack(alignment: .leading, spacing: 10) {
                Text("Section design").font(.headline).foregroundStyle(GummfitTheme.textPrimary)
                ForEach(schema.design.keys.sorted(), id: \.self) { group in
                    DisclosureGroup(group.capitalized) {
                        ForEach(schema.design[group]?.keys.sorted() ?? [], id: \.self) { key in
                            DesignValueRow(label: key, value: currentValue(group: group, key: key)) { value in
                                vm.setDesign(blockKey: blockKey, group: group, key: key, value: value)
                            }
                        }
                    }
                    .tint(GummfitTheme.accent)
                }
            }
            .padding(.top, 10)
        }
    }

    private func currentValue(group: String, key: String) -> JSONValue? {
        vm.blocks.first { $0._k == blockKey }?.design[group]?.objectValue?[key]
    }
}

private struct DesignValueRow: View {
    let label: String
    let value: JSONValue?
    let onChange: (JSONValue) -> Void

    var body: some View {
        HStack {
            Text(label).font(.caption).foregroundStyle(GummfitTheme.textDim)
            Spacer()
            TextField("", text: Binding(get: { value?.stringValue ?? value?.doubleValue.map { String(describing: $0) } ?? "" }, set: { onChange(.string($0)) }))
                .textFieldStyle(.roundedBorder)
                .frame(maxWidth: 150)
        }
    }
}
