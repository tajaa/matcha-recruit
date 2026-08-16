import Foundation

struct FlyerTemplateManifestEntry: Codable, Equatable, Identifiable {
    let id: String
    let name: String
    let preset: String
    let file: String
    let thumb: String?
    let theme: String?
}

struct FlyerPalettePreset: Codable, Equatable, Identifiable {
    let key: String
    let label: String
    let blurb: String
    let colors: [String: String]

    var id: String { key }
}

struct FlyerAiLayout: Codable, Equatable, Identifiable {
    let key: String
    let label: String
    let blurb: String
    let preset: String

    var id: String { key }
}

struct FlyerAiSchema: Codable, Equatable {
    let palette_tokens: [String]
    let palettes: [FlyerPalettePreset]
    let layouts: [FlyerAiLayout]
    let fonts: [String]
    let layer_kinds: [String]
    let addable_layer_kinds: [String]
    let ops: [String]
    let max_ops_per_turn: Int
}
