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
                            DesignValueRow(
                                label: key,
                                spec: schema.designSpec(group: group, key: key),
                                value: currentValue(group: group, key: key)
                            ) { value in
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
    let spec: CappeEditorSchema.DesignSpec
    let value: JSONValue?
    let onChange: (JSONValue) -> Void

    private func deKebab(_ s: String) -> String { s.replacingOccurrences(of: "-", with: " ").capitalized }

    var body: some View {
        switch spec {
        case .enumValues(let options):
            HStack {
                Text(label).font(.caption).foregroundStyle(GummfitTheme.textDim)
                Spacer()
                Picker("", selection: Binding(get: { value?.stringValue ?? "" }, set: { onChange($0.isEmpty ? .null : .string($0)) })) {
                    Text("Default").tag("")
                    ForEach(options, id: \.self) { Text(deKebab($0)).tag($0) }
                }
                .labelsHidden()
            }
        case .bool:
            Toggle(label, isOn: Binding(get: { value?.boolValue ?? false }, set: { onChange(.bool($0)) }))
                .font(.caption)
                .foregroundStyle(GummfitTheme.textDim)
        case .range(let lo, let hi):
            HStack {
                Text(label).font(.caption).foregroundStyle(GummfitTheme.textDim)
                Spacer()
                TextField("", text: Binding(
                    get: { value?.doubleValue.map { String(Int($0)) } ?? "" },
                    set: { text in
                        guard !text.isEmpty else { onChange(.null); return }
                        guard let number = Double(text) else { return }
                        onChange(.number(min(max(number, lo), hi)))
                    }
                ))
                .keyboardType(.numbersAndPunctuation)
                .textFieldStyle(.roundedBorder)
                .frame(maxWidth: 100)
            }
        case .color(let tokens):
            VStack(alignment: .trailing, spacing: 4) {
                HStack {
                    Text(label).font(.caption).foregroundStyle(GummfitTheme.textDim)
                    Spacer()
                    TextField("#1a2b3c", text: Binding(get: { value?.stringValue ?? "" }, set: { onChange(.string($0)) }))
                        .textFieldStyle(.roundedBorder)
                        .textInputAutocapitalization(.never)
                        .frame(maxWidth: 150)
                }
                if !tokens.isEmpty {
                    Text(tokens.joined(separator: ", ")).font(.caption2).foregroundStyle(GummfitTheme.textDim)
                }
            }
        case .text:
            HStack {
                Text(label).font(.caption).foregroundStyle(GummfitTheme.textDim)
                Spacer()
                TextField("", text: Binding(get: { value?.stringValue ?? "" }, set: { onChange(.string($0)) }))
                    .textFieldStyle(.roundedBorder)
                    .frame(maxWidth: 150)
            }
        case .gradient, .unknown:
            HStack {
                Text(label).font(.caption).foregroundStyle(GummfitTheme.textDim)
                Spacer()
                Text("Edit on web").font(.caption).foregroundStyle(GummfitTheme.textDim)
            }
        }
    }
}
