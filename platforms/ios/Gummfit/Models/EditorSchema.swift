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
}

@MainActor
final class SchemaStore {
    static let shared = SchemaStore()

    private(set) var schema: CappeEditorSchema?
    private var loadTask: Task<CappeEditorSchema, Error>?

    private init() {}

    func load() async throws -> CappeEditorSchema {
        if let schema { return schema }
        if let loadTask { return try await loadTask.value }

        let task = Task { try await MerlinService.shared.schema() }
        loadTask = task
        defer { loadTask = nil }
        let value = try await task.value
        schema = value
        return value
    }
}
