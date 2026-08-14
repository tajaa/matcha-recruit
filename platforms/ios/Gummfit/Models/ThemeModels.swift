import Foundation

struct CappeThemeFonts: Codable, Equatable {
    let heading: String?
    let body: String?
}

struct CappeThemeConfig: Codable, Equatable {
    let preset: String?
    let mode: String?
    let fonts: CappeThemeFonts?
    let font: String?
    let radius: String?
    let heroStyle: String?
    let navStyle: String?
    let primaryColor: String?
    let colors: [String: String]?
    let premium: Bool?
    let fancy: Bool?
}

struct CappeThemeSwatch: Equatable {
    let background: String
    let surface: String
    let brand: String
    let text: String
}

struct CappePublishedThemePreset: Identifiable, Equatable {
    let id: String
    let name: String
    let blurb: String
    let premium: Bool
    let swatch: CappeThemeSwatch
    let headingFont: String
    let bodyFont: String
    let mode: String
    let radius: String
}

enum CappePublishedThemeCatalog {
    static let presets: [CappePublishedThemePreset] = [
        .init(id: "clean", name: "Clean", blurb: "Bright, modern, neutral.", premium: false, swatch: .init(background: "#FFFFFF", surface: "#F6F7F9", brand: "#10B981", text: "#16181D"), headingFont: "Inter", bodyFont: "Inter", mode: "light", radius: "lg"),
        .init(id: "minimal", name: "Minimal", blurb: "Quiet, confident, gallery-like.", premium: false, swatch: .init(background: "#FFFFFF", surface: "#F4F4F5", brand: "#18181B", text: "#18181B"), headingFont: "Inter", bodyFont: "Inter", mode: "light", radius: "sm"),
        .init(id: "noir", name: "Noir", blurb: "Dark mode with an electric lime pop.", premium: false, swatch: .init(background: "#0B0B0F", surface: "#15151D", brand: "#A3E635", text: "#F5F6F7"), headingFont: "Inter", bodyFont: "Inter", mode: "dark", radius: "lg"),
        .init(id: "editorial", name: "Editorial", blurb: "Warm and premium with serif headlines.", premium: true, swatch: .init(background: "#FDFBF7", surface: "#F3EEE4", brand: "#B4532A", text: "#1C1A17"), headingFont: "Fraunces", bodyFont: "Inter", mode: "light", radius: "md"),
        .init(id: "studio", name: "Studio", blurb: "Luxe and moody with a gold accent.", premium: true, swatch: .init(background: "#111014", surface: "#1C1A22", brand: "#D4AF37", text: "#F7F5F0"), headingFont: "Playfair Display", bodyFont: "Inter", mode: "dark", radius: "md"),
        .init(id: "sunset", name: "Sunset", blurb: "Friendly, fresh, and softly rounded.", premium: true, swatch: .init(background: "#FFF8F3", surface: "#FFEEE3", brand: "#F0603A", text: "#2A1D18"), headingFont: "Sora", bodyFont: "Inter", mode: "light", radius: "2xl"),
        .init(id: "terra", name: "Terra", blurb: "Grounded and editorial.", premium: true, swatch: .init(background: "#FAF6F0", surface: "#F0E8DB", brand: "#A86B3C", text: "#241F19"), headingFont: "EB Garamond", bodyFont: "Public Sans", mode: "light", radius: "md"),
        .init(id: "cobalt", name: "Cobalt", blurb: "Crisp, confident, and technical.", premium: true, swatch: .init(background: "#FFFFFF", surface: "#EEF2FB", brand: "#2563EB", text: "#0F1729"), headingFont: "Space Grotesk", bodyFont: "Inter", mode: "light", radius: "md"),
        .init(id: "bloom", name: "Bloom", blurb: "Elegant and soft.", premium: true, swatch: .init(background: "#FEF7F6", surface: "#FBE9EA", brand: "#C1466A", text: "#2B1F22"), headingFont: "Cormorant Garamond", bodyFont: "DM Sans", mode: "light", radius: "2xl"),
        .init(id: "press", name: "Press", blurb: "Bold, loud, and headline-first.", premium: true, swatch: .init(background: "#0F0F10", surface: "#1A1A1C", brand: "#F5C518", text: "#F4F4F2"), headingFont: "Anton", bodyFont: "Hanken Grotesk", mode: "dark", radius: "none"),
    ]

    static func resolved(for config: CappeThemeConfig?) -> CappePublishedThemePreset {
        if let id = config?.preset, let preset = presets.first(where: { $0.id == id }) {
            return preset
        }
        return presets[0]
    }
}
