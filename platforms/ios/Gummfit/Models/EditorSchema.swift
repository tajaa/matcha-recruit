import Foundation
import Observation

struct CappeEditorSchema: Codable {
    struct FieldOption: Codable, Hashable {
        let value: String
        let label: String
    }

    struct SubField: Codable, Hashable {
        let kind: String
        let label: String
        let placeholder: String?
        let options: [FieldOption]?
        let item: [String: SubField]?
        let newItem: [String: JSONValue]?
        let addLabel: String?
    }

    struct Field: Codable, Hashable {
        let kind: String
        let label: String
        let placeholder: String?
        let options: [FieldOption]?
        let item: [String: SubField]?
        let newItem: [String: JSONValue]?
        let addLabel: String?
    }

    struct Block: Codable {
        let label: String
        let fields: [String: Field]
        let make: [String: JSONValue]
    }

    struct ThemePreset: Codable, Identifiable {
        let id: String
        let name: String
        let blurb: String
        let premium: Bool
        let mode: String
        let config: [String: JSONValue]
        let swatch: [String: String]
    }

    struct FontPairing: Codable, Identifiable {
        let id: String
        let label: String
        let heading: String
        let body: String
    }

    struct SectionPreset: Codable {
        let name: String
        let label: String
        let blurb: String
        let blockType: String
    }

    struct StyleRecipe: Codable {
        let key: String
        let label: String
        let blurb: String
    }

    struct ThemeInfo: Codable {
        let keys: [String]
        let prefixes: [String]
        let modes: [String]
    }

    struct CanvasLimits: Codable {
        let elementKinds: [String]
        let maxElements: Int
        let gridCols: Int
        let mobileGridCols: Int
    }

    struct Limits: Codable {
        let maxOpsPerTurn: Int
        let canvas: CanvasLimits
    }

    let blocks: [String: Block]
    let blockOrder: [String]
    let design: [String: [String: JSONValue]]
    let theme: ThemeInfo
    let themePresets: [ThemePreset]
    let fontPairings: [FontPairing]
    let sectionPresets: [SectionPreset]
    let styleRecipes: [StyleRecipe]
    let limits: Limits

    func fieldOrder(for blockType: String) -> [String] {
        blocks[blockType].map { $0.fields.keys.sorted() } ?? []
    }

    func preset(_ id: String) -> ThemePreset? {
        themePresets.first { $0.id == id }
    }

    static var offlineFallback: CappeEditorSchema {
        let types = [
            "hero", "features", "split", "bento", "stats", "credentials", "logos", "gallery", "pricing",
            "testimonial", "reviews", "faq", "cta", "store", "booking", "menu", "hours", "map", "posts",
            "text", "contact", "newsletter", "canvas",
        ]
        let blocks = Dictionary(uniqueKeysWithValues: types.map { type in
            (type, Block(label: type, fields: [:], make: ["type": .string(type)]))
        })
        let presets = CappePublishedThemeCatalog.presets.map { preset in
            ThemePreset(
                id: preset.id,
                name: preset.name,
                blurb: preset.blurb,
                premium: preset.premium,
                mode: preset.mode,
                config: fallbackThemeConfig(preset.id) ?? [:],
                swatch: [
                    "bg": preset.swatch.background,
                    "surface": preset.swatch.surface,
                    "brand": preset.swatch.brand,
                    "text": preset.swatch.text,
                ]
            )
        }
        return CappeEditorSchema(
            blocks: blocks,
            blockOrder: types,
            design: [:],
            theme: ThemeInfo(keys: [], prefixes: ["type.", "style."], modes: ["light", "dark"]),
            themePresets: presets,
            fontPairings: [],
            sectionPresets: [],
            styleRecipes: [],
            limits: Limits(
                maxOpsPerTurn: 20,
                canvas: CanvasLimits(elementKinds: ["heading", "text", "image", "button"], maxElements: 200, gridCols: 24, mobileGridCols: 8)
            )
        )
    }
}

func fallbackThemeConfig(_ id: String) -> [String: JSONValue]? {
    guard let preset = CappePublishedThemeCatalog.presets.first(where: { $0.id == id }) else { return nil }
    let centeredNav = ["noir", "studio", "bloom", "press"].contains(id)
    let heroStyle = id == "minimal" ? "minimal" : (id == "editorial" || id == "terra" ? "split" : "centered")
    return [
        "mode": .string(preset.mode),
        "fonts": .object(["heading": .string(preset.headingFont), "body": .string(preset.bodyFont)]),
        "radius": .string(preset.radius),
        "heroStyle": .string(heroStyle),
        "navStyle": .string(centeredNav ? "centered" : "simple"),
        "premium": .bool(preset.premium),
        "colors": .object([
            "bg": .string(preset.swatch.background),
            "surface": .string(preset.swatch.surface),
            "brand": .string(preset.swatch.brand),
            "text": .string(preset.swatch.text),
        ]),
    ]
}

@MainActor
final class SchemaStore {
    static let shared = SchemaStore()

    private(set) var schema: CappeEditorSchema?
    private var loadTask: Task<CappeEditorSchema, Error>?
    private let cacheKey = "cappe.editor.schema"

    private init() {}

    func load() async throws -> CappeEditorSchema {
        if let schema { return schema }
        if let loadTask { return try await loadTask.value }

        if let data = UserDefaults.standard.data(forKey: cacheKey),
           let cached = try? JSONDecoder().decode(CappeEditorSchema.self, from: data) {
            schema = cached
            return cached
        }

        let task = Task { try await MerlinService.shared.schema() }
        loadTask = task
        defer { loadTask = nil }
        do {
            let value = try await task.value
            schema = value
            if let data = try? JSONEncoder().encode(value) {
                UserDefaults.standard.set(data, forKey: cacheKey)
            }
            return value
        } catch let error as APIError {
            switch error {
            case .networkUnavailable, .serviceUnavailable:
                let fallback = CappeEditorSchema.offlineFallback
                schema = fallback
                return fallback
            default:
                throw error
            }
        } catch let error as URLError {
            guard error.code == .notConnectedToInternet || error.code == .cannotConnectToHost || error.code == .timedOut else {
                throw error
            }
            let fallback = CappeEditorSchema.offlineFallback
            schema = fallback
            return fallback
        }
    }
}
