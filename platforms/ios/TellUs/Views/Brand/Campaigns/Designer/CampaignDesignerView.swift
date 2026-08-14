import SwiftUI

struct CampaignDesignerView: View {
    @State private var vm: FlyerDesignerViewModel
    @State private var textDraft = ""
    @State private var shareURL: URL?
    @State private var exportSheet = false
    @State private var shareSheet = false
    @State private var assistant: FlyerAssistantViewModel
    @State private var assistantSheet = false

    init(campaignID: String) {
        _vm = State(initialValue: FlyerDesignerViewModel(campaignID: campaignID))
        _assistant = State(initialValue: FlyerAssistantViewModel())
    }

    private var selectedLayer: DesignLayer? {
        guard let id = vm.selectedLayerID else { return nil }
        return vm.document.design.layers.first { $0.id == id }
    }

    var body: some View {
        Group {
            if vm.isLoading && vm.campaign == nil {
                ProgressView("Loading flyer...")
            } else if let error = vm.error, vm.campaign == nil {
                ContentUnavailableView("Could not load flyer", systemImage: "exclamationmark.triangle", description: Text(error))
            } else {
                editor
            }
        }
        .navigationTitle(vm.campaign?.title ?? "Flyer designer")
        .navigationBarTitleDisplayMode(.inline)
        .task { await vm.load() }
    }

    private var editor: some View {
        VStack(spacing: 0) {
            toolbar
            if let exportError = vm.exportError {
                Text(exportError)
                    .font(.footnote)
                    .foregroundStyle(.red)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal)
                    .padding(.vertical, 6)
            }
            if let saveError = vm.saveError {
                Text(saveError)
                    .font(.footnote)
                    .foregroundStyle(.red)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal)
                    .padding(.vertical, 6)
            }
            FlyerCanvasView(
                design: vm.document.design,
                claimURL: vm.claimURL,
                assets: vm.renderAssets,
                selectedLayerID: vm.selectedLayerID,
                interactive: !vm.isSaving && !assistant.isSending,
                onSelect: { vm.selectLayer($0); syncTextDraft() },
                onLayerChange: { layer, commit in
                    vm.apply(vm.document.design.replacingLayer(layer), commit: commit)
                }
            )
            .frame(minHeight: 300, maxHeight: .infinity)
            .background(Color(uiColor: .secondarySystemBackground))

            Divider()
            inspector
        }
        .onChange(of: vm.selectedLayerID) { _, _ in syncTextDraft() }
        .sheet(isPresented: $exportSheet) {
            FlyerExportSheet(
                onShare: { dpi in
                    do {
                        shareURL = try vm.exportURL(dpi: dpi)
                        exportSheet = false
                        shareSheet = true
                    } catch {}
                },
                onUpload: {
                    Task { await vm.useAsCampaignFlyer(); exportSheet = false }
                }
            )
        }
        .sheet(isPresented: $shareSheet) {
            if let shareURL {
                SharePreviewSheet(url: shareURL)
            }
        }
        .sheet(isPresented: $assistantSheet) {
            FlyerAssistantPanel(
                campaignID: vm.campaignID,
                design: vm.document.design,
                selectedLayer: selectedLayer,
                assets: vm.renderAssets,
                assistant: assistant,
                onDesign: { next in
                    vm.apply(next, commit: true)
                }
            )
        }
    }

    private var toolbar: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                Button { vm.addText() } label: { Label("Text", systemImage: "textformat") }
                Menu {
                    Button("Rectangle") { vm.addShape("rect") }
                    Button("Circle") { vm.addShape("circle") }
                    Button("Line") { vm.addShape("line") }
                } label: {
                    Label("Shape", systemImage: "square.on.circle")
                }
                Button { vm.addQR() } label: { Label("Claim QR", systemImage: "qrcode") }
                    .disabled(vm.document.design.hasUsableQR)
                Menu {
                    ForEach(vm.templates) { template in
                        Button(template.manifest.name) { vm.applyTemplate(template) }
                    }
                } label: {
                    Label("Templates", systemImage: "rectangle.3.group")
                }
                Menu {
                    ForEach(FlyerAssetCatalog.stickerImageNames.keys.sorted(), id: \.self) { assetID in
                        Button(assetID.replacingOccurrences(of: ".svg", with: "")) { vm.addSticker(assetID: assetID) }
                    }
                } label: {
                    Label("Stickers", systemImage: "sparkles")
                }
                Menu {
                    if vm.brand?.logo_url != nil {
                        Button("Add brand logo") { vm.addLogo() }
                    }
                    if vm.palettePresets.isEmpty {
                        Text("Palettes load when the designer opens online")
                    } else {
                        ForEach(vm.palettePresets) { palette in
                            Button(palette.label) { vm.applyPalette(palette.colors) }
                        }
                    }
                    Menu("Artboard") {
                        ForEach(FlyerArtboardPresets.all, id: \.preset) { preset in
                            Button(preset.label) { vm.setArtboard(preset.preset) }
                        }
                    }
                    Button("Warm paper background") { vm.setBackgroundColor("paper") }
                } label: {
                    Label("Brand", systemImage: "paintpalette")
                }
                Divider().frame(height: 24)
                Button { vm.undo() } label: { Image(systemName: "arrow.uturn.backward") }
                    .disabled(!vm.document.canUndo)
                Button { vm.redo() } label: { Image(systemName: "arrow.uturn.forward") }
                    .disabled(!vm.document.canRedo)
                Button {
                    Task { await vm.saveNow() }
                } label: {
                    Label(vm.isSaving ? "Saving..." : "Save", systemImage: "square.and.arrow.down")
                }
                .disabled(!vm.document.isDirty || vm.isSaving)
                Button { exportSheet = true } label: {
                    Label("Export", systemImage: "square.and.arrow.up")
                }
                Button { assistantSheet = true } label: {
                    Label("Assistant", systemImage: "sparkles")
                }
            }
            .buttonStyle(.bordered)
            .controlSize(.small)
            .padding(.horizontal)
            .padding(.vertical, 8)
        }
        .background(.bar)
    }

    @ViewBuilder
    private var inspector: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("Layers").font(.headline)
                Spacer()
                if selectedLayer != nil {
                    Button(role: .destructive) { vm.deleteSelected() } label: {
                        Image(systemName: "trash")
                    }
                    Button { vm.duplicateSelected() } label: {
                        Image(systemName: "plus.square.on.square")
                    }
                }
            }

            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    ForEach(vm.document.design.layers.reversed()) { layer in
                        Button {
                            vm.selectLayer(layer.id)
                        } label: {
                            Text(layer.label)
                                .lineLimit(1)
                                .padding(.horizontal, 9)
                                .padding(.vertical, 6)
                                .background(vm.selectedLayerID == layer.id ? Color.accentColor.opacity(0.2) : Color.secondary.opacity(0.12), in: Capsule())
                        }
                        .foregroundStyle(.primary)
                    }
                }
            }

            if let selectedLayer {
                selectedControls(for: selectedLayer)
            } else {
                Text("Select a layer to edit it, or drag a layer on the canvas.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.horizontal)
        .padding(.vertical, 10)
        .background(.background)
    }

    @ViewBuilder
    private func selectedControls(for layer: DesignLayer) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(layer.label).font(.subheadline.weight(.semibold))
                Spacer()
                Button { vm.reorderSelected(.backward) } label: { Image(systemName: "arrow.down") }
                Button { vm.reorderSelected(.forward) } label: { Image(systemName: "arrow.up") }
            }

            if case .text = layer {
                HStack {
                    TextField("Text", text: $textDraft, axis: .vertical)
                        .textFieldStyle(.roundedBorder)
                    Button("Apply") {
                        vm.updateSelected { selected in
                            guard case .text(var text) = selected else { return selected }
                            text.text = textDraft
                            return .text(text)
                        }
                    }
                    .buttonStyle(.borderedProminent)
                }
            }

            HStack {
                numericField("X", value: layer.origin.x) { value in
                    vm.updateSelected { selected in selected.moved(to: CGPoint(x: value, y: selected.origin.y)) }
                }
                numericField("Y", value: layer.origin.y) { value in
                    vm.updateSelected { selected in selected.moved(to: CGPoint(x: selected.origin.x, y: value)) }
                }
            }
            HStack {
                numericField("Rotation", value: layer.rotation) { value in
                    vm.updateSelected { selected in selected.withRotation(value) }
                }
                Toggle("Lock", isOn: Binding(
                    get: { layer.isLocked },
                    set: { locked in vm.updateSelected { selected in selected.withLock(locked) } }
                ))
                .font(.footnote)
            }
            HStack {
                numericField("Width", value: layer.box.width) { value in
                    vm.updateSelected { selected in selected.withSize(width: value, height: selected.box.height) }
                }
                numericField("Height", value: layer.box.height) { value in
                    vm.updateSelected { selected in selected.withSize(width: selected.box.width, height: value) }
                }
            }
            if case .text(let text) = layer {
                HStack {
                    numericField("Font size", value: text.fontSize) { value in
                        vm.updateSelected { selected in selected.withSize(width: selected.box.width, height: value * text.lineHeight) }
                    }
                    Menu(text.fontFamily) {
                        ForEach(["Helvetica Neue", "Georgia", "Times New Roman", "Trebuchet MS", "Courier New"], id: \.self) { family in
                            Button(family) {
                                vm.updateSelected { selected in selected.withFont(family: family) }
                            }
                        }
                    }
                    .buttonStyle(.bordered)
                }
            }
            VStack(alignment: .leading, spacing: 3) {
                Text("Opacity \(Int(layer.opacity * 100))%")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Slider(value: Binding(
                    get: { layer.opacity },
                    set: { newValue in vm.updateSelected { selected in selected.withOpacity(newValue) } }
                ), in: 0.05...1)
            }
        }
    }

    private func numericField(_ title: String, value: Double, onCommit: @escaping (Double) -> Void) -> some View {
        TextField(title, value: Binding(
            get: { value },
            set: { onCommit($0) }
        ), format: .number)
        .textFieldStyle(.roundedBorder)
        .keyboardType(.numbersAndPunctuation)
    }

    private func syncTextDraft() {
        guard case .text(let layer) = selectedLayer else {
            textDraft = ""
            return
        }
        textDraft = layer.text
    }
}

private struct FlyerExportSheet: View {
    let onShare: (FlyerExportDPI) -> Void
    let onUpload: () -> Void
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            List {
                Section("Download") {
                    ForEach(FlyerExportDPI.allCases) { dpi in
                        Button { onShare(dpi) } label: {
                            Label(dpi.label, systemImage: "arrow.down.circle")
                        }
                    }
                }
                Section("Campaign") {
                    Button { onUpload() } label: {
                        Label("Use as campaign flyer", systemImage: "photo.badge.arrow.down")
                    }
                }
            }
            .navigationTitle("Export flyer")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Close") { dismiss() } }
            }
        }
        .presentationDetents([.medium])
    }
}

private struct SharePreviewSheet: View {
    let url: URL
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            VStack(spacing: 16) {
                Image(systemName: "photo")
                    .font(.system(size: 48))
                    .foregroundStyle(.secondary)
                ShareLink(item: url) {
                    Label("Share PNG", systemImage: "square.and.arrow.up")
                }
                Button("Close") { dismiss() }
            }
            .padding()
            .navigationTitle("Flyer PNG")
            .navigationBarTitleDisplayMode(.inline)
        }
        .presentationDetents([.medium])
    }
}

private extension DesignLayer {
    var label: String {
        switch self {
        case .text(let layer): return String(layer.text.prefix(24)).isEmpty ? "Text" : String(layer.text.prefix(24))
        case .image(let layer): return layer.slot == "logo" ? "Logo" : "Image"
        case .sticker: return "Sticker"
        case .shape(let layer): return layer.shape.capitalized
        case .qr: return "Claim QR"
        case .unknown: return "Unsupported layer"
        }
    }
}
