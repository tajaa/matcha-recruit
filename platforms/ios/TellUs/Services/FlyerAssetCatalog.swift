import Foundation

enum FlyerAssetError: Error, LocalizedError {
    case missingResource(String)
    case invalidManifest

    var errorDescription: String? {
        switch self {
        case .missingResource(let name): return "Flyer asset is missing: \(name)."
        case .invalidManifest: return "The flyer asset manifest is invalid."
        }
    }
}

struct FlyerTemplateAsset: Equatable, Identifiable {
    let manifest: FlyerTemplateManifestEntry
    let design: FlyerDesign

    var id: String { manifest.id }
}

struct FlyerAssetCatalog {
    let bundle: Bundle

    init(bundle: Bundle = .main) {
        self.bundle = bundle
    }

    static let stickerImageNames: [String: String] = [
        "star-burst.svg": "sticker-star-burst",
        "star.svg": "sticker-star",
        "sparkle.svg": "sticker-sparkle",
        "ribbon.svg": "sticker-ribbon",
        "tag.svg": "sticker-tag",
        "coffee-cup.svg": "sticker-coffee-cup",
        "heart.svg": "sticker-heart",
        "arrow-down.svg": "sticker-arrow-down",
    ]

    func templates() throws -> [FlyerTemplateAsset] {
        let manifest: [FlyerTemplateManifestEntry] = try decode(
            resource: "index", fileExtension: "json", subdirectory: "FlyerDesigner/templates"
        )
        return try manifest.map { entry in
            FlyerTemplateAsset(
                manifest: entry,
                design: try decode(
                    resource: entry.file.replacingOccurrences(of: ".json", with: ""),
                    fileExtension: "json",
                    subdirectory: "FlyerDesigner/templates"
                )
            )
        }
    }

    func template(id: String) throws -> FlyerTemplateAsset? {
        try templates().first { $0.id == id }
    }

    func stickerImageName(for assetID: String) -> String? {
        Self.stickerImageNames[assetID]
    }

    private func decode<T: Decodable>(resource: String, fileExtension: String, subdirectory: String) throws -> T {
        let url = bundle.url(forResource: resource, withExtension: fileExtension, subdirectory: subdirectory)
            ?? bundle.url(forResource: resource, withExtension: fileExtension)
        guard let url else {
            throw FlyerAssetError.missingResource("\(subdirectory)/\(resource).\(fileExtension)")
        }
        do {
            return try JSONDecoder().decode(T.self, from: Data(contentsOf: url))
        } catch {
            throw FlyerAssetError.invalidManifest
        }
    }
}
