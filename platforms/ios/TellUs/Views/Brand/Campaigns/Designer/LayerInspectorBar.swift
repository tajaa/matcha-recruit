import SwiftUI

struct LayerInspectorBar: View {
    let design: FlyerDesign
    let layers: [DesignLayer]
    let selectedLayerID: String?
    let brandLogoAvailable: Bool
    let onSelect: (String?) -> Void
    let onDelete: () -> Void
    let onDuplicate: () -> Void
    let onReorder: (FlyerLayerDirection) -> Void
    let onUpdate: (DesignLayer) -> Void
    let onAddLogo: () -> Void
    @Binding var textDraft: String

    private let colorTokens = ["ink", "paper", "brand", "brandSoft", "accent", "muted"]

    private var selectedLayer: DesignLayer? {
        guard let selectedLayerID else { return nil }
        return layers.first { $0.id == selectedLayerID }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("Layers").font(.interHeadline)
                Spacer()
                if selectedLayer != nil {
                    Button(role: .destructive, action: onDelete) { Image(systemName: "trash") }
                    Button(action: onDuplicate) { Image(systemName: "plus.square.on.square") }
                }
            }

            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    ForEach(layers.reversed()) { layer in
                        Button { onSelect(layer.id) } label: {
                            Text(label(for: layer))
                                .lineLimit(1)
                                .padding(.horizontal, 9)
                                .padding(.vertical, 6)
                                .background(selectedLayerID == layer.id ? Color.accentColor.opacity(0.2) : Color.secondary.opacity(0.12), in: Capsule())
                        }
                        .foregroundStyle(.primary)
                    }
                }
            }

            if let selectedLayer {
                controls(for: selectedLayer)
            } else {
                Text("Select a layer to edit it, or use the canvas gestures.")
                    .font(.interFootnote)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.horizontal)
        .padding(.vertical, 10)
        .background(.background)
    }

    @ViewBuilder
    private func controls(for layer: DesignLayer) -> some View {
        HStack {
            Text(label(for: layer)).font(.subheadline.weight(.semibold))
            Spacer()
            Button { onReorder(.backward) } label: { Image(systemName: "arrow.down") }
            Button { onReorder(.forward) } label: { Image(systemName: "arrow.up") }
        }

        switch layer {
        case .text:
            TextField("Text", text: $textDraft, axis: .vertical)
                .textFieldStyle(.roundedBorder)
                .onSubmit { updateText(layer, text: textDraft) }
            if case .text(let text) = layer {
                HStack {
                    ForEach(["Helvetica Neue", "Georgia", "Times New Roman", "Trebuchet MS", "Courier New"], id: \.self) { family in
                        Button(family) { onUpdate(layer.withFont(family: family)) }
                            .font(.caption2)
                            .buttonStyle(.bordered)
                            .tint(text.fontFamily == family ? .accentColor : .secondary)
                    }
                }
                .scrollableIfNeeded()
                Stepper("Size \(Int(text.fontSize))", value: Binding(
                    get: { text.fontSize },
                    set: { onUpdate(layer.withSize(width: text.width, height: $0 * text.lineHeight)) }
                ), in: FlyerLayerLimits.textFontSize, step: 1)
                swatches(for: layer)
            }
        case .sticker, .shape:
            sizeSlider(for: layer)
            swatches(for: layer)
        case .qr:
            Text("Claim code colors").font(.interCaption).foregroundStyle(.secondary)
            qrSwatches(for: layer)
        case .image:
            opacitySlider(for: layer)
            if brandLogoAvailable {
                Button("Replace with brand logo", action: onAddLogo)
                    .buttonStyle(.bordered)
            }
        case .unknown:
            EmptyView()
        }

        DisclosureGroup("Precise") {
            HStack {
                numericField("X", value: layer.origin.x) { onUpdate(layer.moved(to: CGPoint(x: $0, y: layer.origin.y))) }
                numericField("Y", value: layer.origin.y) { onUpdate(layer.moved(to: CGPoint(x: layer.origin.x, y: $0))) }
            }
            HStack {
                numericField("Width", value: layer.box.width) { onUpdate(layer.withSize(width: $0, height: layer.box.height)) }
                numericField("Height", value: layer.box.height) { onUpdate(layer.withSize(width: layer.box.width, height: $0)) }
            }
            HStack {
                numericField("Rotation", value: layer.rotation) { onUpdate(layer.withRotation($0)) }
                Toggle("Lock", isOn: Binding(
                    get: { layer.isLocked },
                    set: { onUpdate(layer.withLock($0)) }
                ))
                .font(.interFootnote)
            }
        }
    }

    private func updateText(_ layer: DesignLayer, text: String) {
        guard case .text(var value) = layer else { return }
        value.text = text
        onUpdate(.text(value))
    }

    private func sizeSlider(for layer: DesignLayer) -> some View {
        Slider(value: Binding(
            get: { min(800, max(8, layer.box.width)) },
            set: { onUpdate(layer.withSize(width: $0, height: layer.box.height * ($0 / max(0.01, layer.box.width)))) }
        ), in: 8...800)
    }

    private func opacitySlider(for layer: DesignLayer) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text("Opacity \(Int(layer.opacity * 100))%")
                .font(.interCaption)
                .foregroundStyle(.secondary)
            Slider(value: Binding(
                get: { layer.opacity },
                set: { onUpdate(layer.withOpacity($0)) }
            ), in: FlyerLayerLimits.opacity)
        }
    }

    private func swatches(for layer: DesignLayer) -> some View {
        HStack(spacing: 8) {
            ForEach(colorTokens, id: \.self) { token in
                Button { onUpdate(layer.withFill(token)) } label: {
                    Circle()
                        .fill(resolveFlyerColor(token, palette: design.palette))
                        .frame(width: 24, height: 24)
                        .overlay(Circle().stroke(.primary.opacity(0.2)))
                }
                .accessibilityLabel(token)
            }
        }
    }

    private func qrSwatches(for layer: DesignLayer) -> some View {
        HStack {
            ForEach(colorTokens, id: \.self) { token in
                Button("FG \(token)") { onUpdate(layer.withQRForeground(token)) }
                    .font(.caption2)
                    .buttonStyle(.bordered)
                Button("BG \(token)") { onUpdate(layer.withQRBackground(token)) }
                    .font(.caption2)
                    .buttonStyle(.bordered)
            }
        }
        .scrollableIfNeeded()
    }

    private func numericField(_ title: String, value: CGFloat, onCommit: @escaping (Double) -> Void) -> some View {
        DesignerNumericField(title: title, value: Double(value), onCommit: onCommit)
    }

    private func label(for layer: DesignLayer) -> String {
        switch layer {
        case .text(let value): return String(value.text.prefix(24)).isEmpty ? "Text" : String(value.text.prefix(24))
        case .image(let value): return value.slot == "logo" ? "Logo" : "Image"
        case .sticker: return "Sticker"
        case .shape(let value): return value.shape.capitalized
        case .qr: return "Claim QR"
        case .unknown: return "Unsupported layer"
        }
    }
}

private struct DesignerNumericField: View {
    let title: String
    let value: Double
    let onCommit: (Double) -> Void
    @State private var draft: Double

    init(title: String, value: Double, onCommit: @escaping (Double) -> Void) {
        self.title = title
        self.value = value
        self.onCommit = onCommit
        _draft = State(initialValue: value)
    }

    var body: some View {
        TextField(title, value: $draft, format: .number)
            .textFieldStyle(.roundedBorder)
            .keyboardType(.numbersAndPunctuation)
            .onSubmit { onCommit(draft) }
            .onChange(of: value) { _, newValue in draft = newValue }
    }
}

private extension DesignLayer {
    func withFill(_ value: String) -> DesignLayer {
        switch self {
        case .text(var layer): layer.fill = value; return .text(layer)
        case .shape(var layer): layer.fill = value; return .shape(layer)
        default: return self
        }
    }

    func withQRForeground(_ value: String) -> DesignLayer {
        guard case .qr(var layer) = self else { return self }
        layer.fg = value
        return .qr(layer)
    }

    func withQRBackground(_ value: String) -> DesignLayer {
        guard case .qr(var layer) = self else { return self }
        layer.bg = value
        return .qr(layer)
    }
}

private extension View {
    @ViewBuilder
    func scrollableIfNeeded() -> some View {
        ScrollView(.horizontal, showsIndicators: false) { self }
    }
}
