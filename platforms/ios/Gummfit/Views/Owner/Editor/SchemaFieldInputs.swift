import SwiftUI

struct SchemaFieldInput: View {
    let field: CappeEditorSchema.Field
    let path: String
    let value: JSONValue?
    let onChange: (String, JSONValue) -> Void
    let siteId: String

    var body: some View {
        fieldBody
            .padding(.vertical, 4)
    }

    @ViewBuilder
    private var fieldBody: some View {
        switch field.kind {
        case "textarea":
            VStack(alignment: .leading, spacing: 5) {
                Text(field.label).font(.caption.weight(.semibold)).foregroundStyle(GummfitTheme.textDim)
                TextEditor(text: textBinding)
                    .frame(minHeight: 76)
                    .padding(6)
                    .background(GummfitTheme.backgroundRaised, in: RoundedRectangle(cornerRadius: 8))
            }
        case "select":
            Picker(field.label, selection: stringBinding) {
                ForEach(field.options ?? [], id: \.value) { option in Text(option.label).tag(option.value) }
            }
            .pickerStyle(.menu)
        case "bool":
            Toggle(field.label, isOn: boolBinding)
        case "strlist":
            StringListInput(field: field, path: path, value: value, onChange: onChange)
        case "list":
            NestedListInput(field: field, path: path, value: value, onChange: onChange, siteId: siteId)
        case "image", "video":
            VStack(alignment: .leading, spacing: 5) {
                Text(field.label).font(.caption.weight(.semibold)).foregroundStyle(GummfitTheme.textDim)
                TextField(field.placeholder ?? "Asset URL", text: textBinding)
                    .textFieldStyle(.roundedBorder)
                    .textInputAutocapitalization(.never)
            }
        default:
            TextField(field.label, text: textBinding, prompt: field.placeholder.map(Text.init))
                .textFieldStyle(.roundedBorder)
        }
    }

    private var textBinding: Binding<String> {
        Binding(get: { value?.stringValue ?? "" }, set: { onChange(path, .string($0)) })
    }

    private var stringBinding: Binding<String> { textBinding }
    private var boolBinding: Binding<Bool> {
        Binding(get: { value?.boolValue ?? false }, set: { onChange(path, .bool($0)) })
    }
}

private struct StringListInput: View {
    let field: CappeEditorSchema.Field
    let path: String
    let value: JSONValue?
    let onChange: (String, JSONValue) -> Void

    var strings: [JSONValue] { value?.arrayValue ?? [] }

    var body: some View {
        VStack(alignment: .leading, spacing: 7) {
            Text(field.label).font(.caption.weight(.semibold)).foregroundStyle(GummfitTheme.textDim)
            ForEach(strings.indices, id: \.self) { index in
                HStack {
                    TextField("Item", text: Binding(
                        get: { strings[index].stringValue ?? "" },
                        set: { newValue in var next = strings; next[index] = .string(newValue); onChange(path, .array(next)) }
                    ))
                    Button { var next = strings; next.remove(at: index); onChange(path, .array(next)) } label: { Image(systemName: "minus.circle") }.foregroundStyle(GummfitTheme.danger)
                }
            }
            Button(field.addLabel ?? "Add item") { onChange(path, .array(strings + [.string("")])) }
                .font(.caption.weight(.semibold))
                .foregroundStyle(GummfitTheme.accent)
        }
    }
}

private struct NestedListInput: View {
    let field: CappeEditorSchema.Field
    let path: String
    let value: JSONValue?
    let onChange: (String, JSONValue) -> Void
    let siteId: String

    var rows: [JSONValue] { value?.arrayValue ?? [] }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(field.label).font(.caption.weight(.semibold)).foregroundStyle(GummfitTheme.textDim)
            ForEach(rows.indices, id: \.self) { index in
                VStack(alignment: .leading, spacing: 5) {
                    HStack {
                        Text("Row \(index + 1)").font(.caption.weight(.bold))
                        Spacer()
                        Button { var next = rows; next.remove(at: index); onChange(path, .array(next)) } label: { Image(systemName: "trash") }.foregroundStyle(GummfitTheme.danger)
                    }
                    ForEach((field.item ?? [:]).keys.sorted(), id: \.self) { key in
                        if let subfield = field.item?[key] {
                            SchemaSubFieldInput(field: subfield, path: "\(path).\(index).\(key)", value: rows[index].objectValue?[key], onChange: onChange, siteId: siteId)
                        }
                    }
                }
                .padding(10)
                .background(GummfitTheme.backgroundRaised, in: RoundedRectangle(cornerRadius: 10))
            }
            Button(field.addLabel ?? "Add item") {
                onChange(path, .array(rows + [.object(field.newItem ?? [:])]))
            }
            .font(.caption.weight(.semibold))
            .foregroundStyle(GummfitTheme.accent)
        }
    }
}

private struct SchemaSubFieldInput: View {
    let field: CappeEditorSchema.SubField
    let path: String
    let value: JSONValue?
    let onChange: (String, JSONValue) -> Void
    let siteId: String

    var body: some View {
        switch field.kind {
        case "textarea":
            TextField(field.label, text: textBinding, axis: .vertical).textFieldStyle(.roundedBorder)
        case "select":
            Picker(field.label, selection: textBinding) {
                ForEach(field.options ?? [], id: \.value) { option in Text(option.label).tag(option.value) }
            }.pickerStyle(.menu)
        case "bool":
            Toggle(field.label, isOn: boolBinding)
        case "list":
            NestedListInput(field: CappeEditorSchema.Field(kind: field.kind, label: field.label, placeholder: field.placeholder, options: field.options, item: field.item, newItem: field.newItem, addLabel: field.addLabel), path: path, value: value, onChange: onChange, siteId: siteId)
        default:
            TextField(field.label, text: textBinding, prompt: field.placeholder.map(Text.init)).textFieldStyle(.roundedBorder)
        }
    }

    private var textBinding: Binding<String> { Binding(get: { value?.stringValue ?? "" }, set: { onChange(path, .string($0)) }) }
    private var boolBinding: Binding<Bool> { Binding(get: { value?.boolValue ?? false }, set: { onChange(path, .bool($0)) }) }
}
