import Foundation
import Observation
import UIKit

@MainActor
@Observable
final class FlyerDesignerViewModel: LoadableVM {
    let campaignID: String
    let document: FlyerDocumentStore
    let assetCatalog: FlyerAssetCatalog
    let templates: [FlyerTemplateAsset]

    var campaign: PromoCampaign?
    var brand: Brand?
    var logoImage: UIImage?
    var imageAssets: [String: UIImage] = [:]
    var selectedLayerID: String?
    var isLoading = false
    var error: String?
    var isSaving = false
    var saveError: String?
    var exportError: String?
    var flyerImageURL: String?
    var palettePresets: [FlyerPalettePreset] = []
    var currentTheme: String?

    var isReady: Bool { isLoaded }

    private var autosaveTask: Task<Void, Never>?
    private var isLoaded = false

    init(campaignID: String, assetCatalog: FlyerAssetCatalog = FlyerAssetCatalog()) {
        self.campaignID = campaignID
        self.assetCatalog = assetCatalog
        templates = (try? assetCatalog.templates()) ?? []
        document = FlyerDocumentStore(FlyerDesignFactory.blank())
    }

    var claimURL: String {
        guard let campaign else { return "" }
        return APIClient.shared.webOrigin + campaign.claim_url
    }

    var renderAssets: FlyerRenderAssets {
        FlyerRenderAssets.bundled.withLogo(logoImage).withImages(imageAssets)
    }

    func load() async {
        isLoaded = false
        isLoading = true
        defer { isLoading = false }
        do {
            async let campaignRequest = PromoService.shared.campaign(id: campaignID)
            async let brandRequest = BrandAdminService.shared.brand()
            async let designRequest = PromoService.shared.design(campaignId: campaignID)
            let (loadedCampaign, loadedBrand, envelope) = try await (campaignRequest, brandRequest, designRequest)
            campaign = loadedCampaign
            brand = loadedBrand
            flyerImageURL = loadedCampaign.flyer_image_url
            let loadedDesign = envelope.design_json ?? FlyerDesignFactory.starter(
                campaign: loadedCampaign,
                logoURL: loadedBrand.logo_url
            )
            document.reset(to: loadedDesign)
            selectedLayerID = nil
            currentTheme = nil
            isLoaded = true
            error = nil
            saveError = nil
            await loadLogo(urlString: loadedBrand.logo_url)
            await loadImages(for: loadedDesign)
            Task { @MainActor [weak self] in
                self?.palettePresets = (try? await FlyerAiService.shared.schema().palettes) ?? []
            }
        } catch {
            if !error.isCancellation { self.error = error.localizedDescription }
        }
    }

    func selectLayer(_ id: String?) {
        selectedLayerID = id
    }

    func apply(_ next: FlyerDesign, commit: Bool) {
        guard isLoaded else { return }
        document.apply(next, commit: commit)
        loadImagesInBackground(for: next)
        scheduleAutosave()
    }

    func addText() {
        apply(document.design.appending(FlyerDesignFactory.text(in: document.design, text: "Your headline")), commit: true)
    }

    func addShape(_ shape: String) {
        apply(document.design.appending(FlyerDesignFactory.shape(in: document.design, shape: shape)), commit: true)
    }

    func addQR() {
        guard !document.design.hasUsableQR else { return }
        apply(document.design.appending(FlyerDesignFactory.qr(in: document.design)), commit: true)
    }

    func addSticker(assetID: String) {
        apply(document.design.appending(FlyerDesignFactory.sticker(in: document.design, assetID: assetID)), commit: true)
    }

    func addLogo() {
        guard let logoURL = brand?.logo_url else { return }
        apply(document.design.appending(FlyerDesignFactory.image(in: document.design, source: logoURL, size: CGSize(width: 512, height: 512), slot: "logo")), commit: true)
    }

    func replaceSelectedWithLogo() {
        guard let logoURL = brand?.logo_url else { return }
        updateSelected { selected in
            guard case .image(var image) = selected else { return selected }
            image.src = logoURL
            image.slot = "logo"
            return .image(image)
        }
    }

    func applyTemplate(_ template: FlyerTemplateAsset) {
        apply(FlyerDesignFactory.instantiate(template.design, logoURL: brand?.logo_url), commit: true)
        selectedLayerID = nil
        currentTheme = template.manifest.theme
    }

    func deleteSelected() {
        guard let selectedLayerID else { return }
        apply(document.design.removingLayer(id: selectedLayerID), commit: true)
        self.selectedLayerID = nil
    }

    func duplicateSelected() {
        guard let selectedLayerID else { return }
        apply(document.design.duplicatingLayer(id: selectedLayerID), commit: true)
    }

    func reorderSelected(_ direction: FlyerLayerDirection) {
        guard let selectedLayerID else { return }
        apply(document.design.reorderingLayer(id: selectedLayerID, direction: direction), commit: true)
    }

    func updateSelected(_ mutation: (DesignLayer) -> DesignLayer) {
        guard let selectedLayerID, let layer = document.design.layers.first(where: { $0.id == selectedLayerID }) else { return }
        apply(document.design.replacingLayer(mutation(layer)), commit: true)
    }

    func undo() {
        document.undo()
        scheduleAutosave()
    }

    func redo() {
        document.redo()
        scheduleAutosave()
    }

    func applyPalette(_ colors: [String: String]) {
        var design = document.design
        design.palette = colors
        apply(design, commit: true)
    }

    func setBackgroundColor(_ color: String) {
        var design = document.design
        design.background = FlyerBackground(kind: "color", color: color, src: nil, fit: nil)
        apply(design, commit: true)
    }

    func setArtboard(_ preset: String) {
        apply(document.design.retargeted(to: preset), commit: true)
    }

    func exportURL(dpi: FlyerExportDPI) throws -> URL {
        exportError = nil
        do {
            return try FlyerExportService.writePNG(
                design: document.design,
                claimURL: claimURL,
                assets: renderAssets,
                dpi: dpi
            )
        } catch {
            exportError = error.localizedDescription
            throw error
        }
    }

    func useAsCampaignFlyer() async {
        do {
            let url = try exportURL(dpi: .dpi150)
            let response = try await PromoService.shared.uploadFlyer(
                campaignId: campaignID,
                pngData: try Data(contentsOf: url)
            )
            flyerImageURL = response.flyer_image_url
            exportError = nil
        } catch {
            if !error.isCancellation { exportError = error.localizedDescription }
        }
    }

    func saveNow() async {
        guard isLoaded, document.isDirty, !isSaving else { return }
        let snapshot = document.snapshotForSave()
        isSaving = true
        saveError = nil
        defer { isSaving = false }
        do {
            try await PromoService.shared.saveDesign(campaignId: campaignID, design: snapshot.design)
            document.markSaved(snapshot)
            if document.isDirty { scheduleAutosave() }
        } catch {
            if !error.isCancellation { saveError = error.localizedDescription }
        }
    }

    private func scheduleAutosave() {
        guard isLoaded else { return }
        autosaveTask?.cancel()
        autosaveTask = Task { @MainActor [weak self] in
            do {
                try await Task.sleep(for: .seconds(2))
                guard !Task.isCancelled else { return }
                await self?.saveNow()
            } catch {
                // Cancellation is the normal path when edits arrive in a burst.
            }
        }
    }

    private func loadLogo(urlString: String?) async {
        guard let urlString, let url = URL(string: urlString) else {
            logoImage = nil
            return
        }
        do {
            let (data, _) = try await URLSession.shared.data(from: url)
            if !Task.isCancelled { logoImage = UIImage(data: data)?.normalizedUp() }
        } catch {
            logoImage = nil
        }
    }

    private var loadingImageSources = Set<String>()

    private func loadImagesInBackground(for design: FlyerDesign) {
        for source in imageSources(in: design) where imageAssets[source] == nil && !loadingImageSources.contains(source) {
            loadingImageSources.insert(source)
            Task { @MainActor [weak self] in
                await self?.loadImage(source: source)
            }
        }
    }

    private func loadImages(for design: FlyerDesign) async {
        for source in imageSources(in: design) where imageAssets[source] == nil {
            if !loadingImageSources.contains(source) {
                loadingImageSources.insert(source)
            }
            await loadImage(source: source)
        }
    }

    private func imageSources(in design: FlyerDesign) -> Set<String> {
        Set(design.layers.compactMap { layer in
            guard case .image(let image) = layer, image.slot != "logo", !image.src.isEmpty else { return nil }
            return image.src
        })
    }

    private func loadImage(source: String) async {
        defer { loadingImageSources.remove(source) }
        guard imageAssets[source] == nil, let url = URL(string: source) else { return }
        do {
            let (data, _) = try await URLSession.shared.data(from: url)
            guard !Task.isCancelled, let image = UIImage(data: data) else { return }
            imageAssets[source] = image.normalizedUp()
        } catch {
            // A missing optional image should not block editing the rest of the flyer.
        }
    }
}

private extension FlyerDesign {
    func appending(_ layer: DesignLayer) -> FlyerDesign {
        var copy = self
        copy.layers.append(layer)
        return copy
    }
}
