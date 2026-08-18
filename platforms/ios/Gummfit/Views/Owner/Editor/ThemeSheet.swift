import SwiftUI

struct ThemeSheet: View {
    @Bindable var vm: PageEditorViewModel
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                Text("Theme presets").font(.headline).foregroundStyle(GummfitTheme.textPrimary)
                LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 10) {
                    ForEach(vm.schema?.themePresets ?? [], id: \.id) { preset in
                        Button {
                            vm.setThemeKey("preset", .string(preset.id))
                        } label: {
                            VStack(alignment: .leading, spacing: 8) {
                                HStack {
                                    Circle().fill(Color(hex: preset.swatch["brand"] ?? "#10B981")).frame(width: 22, height: 22)
                                    Text(preset.name).font(.subheadline.weight(.semibold))
                                }
                                Text(preset.blurb).font(.caption2).foregroundStyle(GummfitTheme.textDim).lineLimit(2)
                            }
                            .frame(maxWidth: .infinity, minHeight: 82, alignment: .leading)
                            .padding(12)
                            .background(GummfitTheme.surface, in: RoundedRectangle(cornerRadius: 12))
                        }
                        .buttonStyle(.plain)
                    }
                }
                VStack(alignment: .leading, spacing: 10) {
                    Text("Brand color").font(.headline).foregroundStyle(GummfitTheme.textPrimary)
                    TextField("#10B981", text: Binding(get: { vm.theme["colors"]?.objectValue?["brand"]?.stringValue ?? "" }, set: { vm.setThemeKey("colors.brand", .string($0)) }))
                        .textFieldStyle(.roundedBorder)
                        .textInputAutocapitalization(.characters)
                    Picker("Mode", selection: Binding(get: { vm.theme["mode"]?.stringValue ?? "light" }, set: { vm.setThemeKey("mode", .string($0)) })) {
                        Text("Light").tag("light")
                        Text("Dark").tag("dark")
                    }
                    Picker("Corners", selection: Binding(get: { vm.theme["radius"]?.stringValue ?? "lg" }, set: { vm.setThemeKey("radius", .string($0)) })) {
                        ForEach(["none", "sm", "md", "lg", "xl", "2xl"], id: \.self) { Text($0.uppercased()).tag($0) }
                    }
                }
                if let pairings = vm.schema?.fontPairings, !pairings.isEmpty {
                    Picker("Font pairing", selection: Binding(get: { vm.theme["fonts"]?.objectValue?["heading"]?.stringValue ?? "Inter" }, set: { value in
                        guard let pairing = pairings.first(where: { $0.heading == value }) else { return }
                        vm.setThemeKey("fonts.heading", .string(pairing.heading))
                        vm.setThemeKey("fonts.body", .string(pairing.body))
                    })) {
                        ForEach(pairings, id: \.id) { Text($0.label).tag($0.heading) }
                    }
                }
            }
            .padding()
        }
        .navigationTitle("Theme")
        .toolbar { ToolbarItem(placement: .topBarLeading) { Button("Done") { dismiss() } } }
        .gummfitScreenChrome()
    }
}
