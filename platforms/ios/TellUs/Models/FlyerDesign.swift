import Foundation
import SwiftUI

// Mirrors client/tellus/src/api/types.ts's FlyerDesign and
// server/app/tellus/services/flyer_ai/catalog.py.
//
// Round-trip fidelity is the priority: a layer kind THIS build doesn't know
// decodes to `.unknown` and re-encodes verbatim, so opening a design on the
// phone and saving it can't quietly delete something a newer web build
// authored. Unknown FIELDS on a *known* kind are still dropped — accepted for
// now, and the reason the document carries a `version`.

// MARK: - Palette

enum FlyerPaletteToken: String, CaseIterable {
    case ink, paper, brand, brandSoft, accent, muted
}

let DEFAULT_FLYER_PALETTE: [String: String] = [
    "ink": "#17140f", "paper": "#f3ede0", "brand": "#f97316",
    "brandSoft": "#fb923c", "accent": "#34d399", "muted": "#8a8371",
]

/// Token -> hex, hex -> itself. Mirrors utils/designer.ts:resolveColor,
/// including the fall-through to the default palette for a token the document
/// doesn't define — losing a custom shade beats painting the layer black.
func resolveFlyerColor(_ value: String, palette: [String: String]?) -> Color {
    let hex: String
    if value.hasPrefix("#") {
        hex = value
    } else if let fromDoc = palette?[value] {
        hex = fromDoc
    } else {
        hex = DEFAULT_FLYER_PALETTE[value] ?? DEFAULT_FLYER_PALETTE["ink"]!
    }
    return Color(hex: hex)
}

extension Color {
    init(hex: String) {
        var raw = hex.trimmingCharacters(in: CharacterSet(charactersIn: "#"))
        if raw.count == 3 { raw = raw.map { "\($0)\($0)" }.joined() }
        let value = UInt64(raw, radix: 16) ?? 0
        self.init(
            .sRGB,
            red: Double((value >> 16) & 0xff) / 255,
            green: Double((value >> 8) & 0xff) / 255,
            blue: Double(value & 0xff) / 255,
            opacity: 1
        )
    }
}

/// Web offers eight families; three of them ship on macOS/Windows but not iOS,
/// and a missing family silently reflows a print export. The AI is pinned to the
/// portable five (catalog.FONT_FAMILIES); this map covers a human-authored
/// design that used one of the others.
let FONT_FALLBACKS: [String: String] = [
    "Arial Black": "Avenir Next Heavy",
    "Impact": "Futura-CondensedExtraBold",
    "Brush Script MT": "SnellRoundhand-Black",
]

func flyerFontName(_ family: String) -> String {
    FONT_FALLBACKS[family] ?? family
}

// MARK: - Layers

struct FlyerArtboard: Codable, Equatable {
    var preset: String
    var w: Double
    var h: Double
}

struct FlyerBackground: Codable, Equatable {
    var kind: String
    var color: String?
    var src: String?
    var fit: String?
}

struct TextLayer: Codable, Equatable {
    var id: String
    var x: Double, y: Double, rotation: Double, opacity: Double
    var locked: Bool?
    var text: String
    var fontFamily: String
    var fontSize: Double
    var fontStyle: String
    var fill: String
    var align: String
    var width: Double
    var lineHeight: Double
    var letterSpacing: Double
}

struct ImageLayer: Codable, Equatable {
    var id: String
    var x: Double, y: Double, rotation: Double, opacity: Double
    var locked: Bool?
    var src: String
    var width: Double, height: Double
    var slot: String?
}

struct StickerLayer: Codable, Equatable {
    var id: String
    var x: Double, y: Double, rotation: Double, opacity: Double
    var locked: Bool?
    var assetId: String
    var width: Double, height: Double
}

struct ShapeLayer: Codable, Equatable {
    var id: String
    var x: Double, y: Double, rotation: Double, opacity: Double
    var locked: Bool?
    var shape: String
    var width: Double, height: Double
    var fill: String
    var stroke: String?
    var strokeWidth: Double?
    var cornerRadius: Double?
}

struct QRLayer: Codable, Equatable {
    var id: String
    var x: Double, y: Double, rotation: Double, opacity: Double
    var locked: Bool?
    var size: Double
    var fg: String
    var bg: String
}

enum DesignLayer: Codable, Equatable, Identifiable {
    case text(TextLayer)
    case image(ImageLayer)
    case sticker(StickerLayer)
    case shape(ShapeLayer)
    case qr(QRLayer)
    case unknown(id: String, raw: JSONValue)

    private enum TypeKey: String, CodingKey { case type, id }

    var id: String {
        switch self {
        case .text(let l): return l.id
        case .image(let l): return l.id
        case .sticker(let l): return l.id
        case .shape(let l): return l.id
        case .qr(let l): return l.id
        case .unknown(let id, _): return id
        }
    }

    var kind: String {
        switch self {
        case .text: return "text"
        case .image: return "image"
        case .sticker: return "sticker"
        case .shape: return "shape"
        case .qr: return "qr"
        case .unknown: return "unknown"
        }
    }

    var isLocked: Bool {
        switch self {
        case .text(let l): return l.locked ?? false
        case .image(let l): return l.locked ?? false
        case .sticker(let l): return l.locked ?? false
        case .shape(let l): return l.locked ?? false
        case .qr(let l): return l.locked ?? false
        case .unknown: return true
        }
    }

    /// Origin in artboard units. Every layer stores its TOP-LEFT corner.
    var origin: CGPoint {
        switch self {
        case .text(let l): return CGPoint(x: l.x, y: l.y)
        case .image(let l): return CGPoint(x: l.x, y: l.y)
        case .sticker(let l): return CGPoint(x: l.x, y: l.y)
        case .shape(let l): return CGPoint(x: l.x, y: l.y)
        case .qr(let l): return CGPoint(x: l.x, y: l.y)
        case .unknown: return .zero
        }
    }

    /// Occupied box. A text layer's height is DERIVED (fontSize x lineHeight),
    /// not stored — one definition shared by hit-testing, snapping and bounds,
    /// matching utils/designer.ts:layerBox.
    var box: CGSize {
        switch self {
        case .text(let l): return CGSize(width: l.width, height: l.fontSize * l.lineHeight)
        case .image(let l): return CGSize(width: l.width, height: l.height)
        case .sticker(let l): return CGSize(width: l.width, height: l.height)
        case .shape(let l): return CGSize(width: l.width, height: l.height)
        case .qr(let l): return CGSize(width: l.size, height: l.size)
        case .unknown: return .zero
        }
    }

    var rotation: Double {
        switch self {
        case .text(let l): return l.rotation
        case .image(let l): return l.rotation
        case .sticker(let l): return l.rotation
        case .shape(let l): return l.rotation
        case .qr(let l): return l.rotation
        case .unknown: return 0
        }
    }

    var opacity: Double {
        switch self {
        case .text(let l): return l.opacity
        case .image(let l): return l.opacity
        case .sticker(let l): return l.opacity
        case .shape(let l): return l.opacity
        case .qr(let l): return l.opacity
        case .unknown: return 1
        }
    }

    func moved(to point: CGPoint) -> DesignLayer {
        switch self {
        case .text(var l): l.x = point.x; l.y = point.y; return .text(l)
        case .image(var l): l.x = point.x; l.y = point.y; return .image(l)
        case .sticker(var l): l.x = point.x; l.y = point.y; return .sticker(l)
        case .shape(var l): l.x = point.x; l.y = point.y; return .shape(l)
        case .qr(var l): l.x = point.x; l.y = point.y; return .qr(l)
        case .unknown: return self
        }
    }

    /// Konva stores real width/height rather than a scale factor, and so does
    /// this — font metrics and export maths stay in artboard units.
    func resized(to size: CGSize) -> DesignLayer {
        switch self {
        case .text(var l):
            l.width = max(24, size.width)
            l.fontSize = max(8, l.fontSize * (size.height / max(1, l.fontSize * l.lineHeight)))
            return .text(l)
        case .image(var l): l.width = max(8, size.width); l.height = max(8, size.height); return .image(l)
        case .sticker(var l): l.width = max(8, size.width); l.height = max(8, size.height); return .sticker(l)
        case .shape(var l): l.width = max(4, size.width); l.height = max(2, size.height); return .shape(l)
        case .qr(var l): l.size = max(96, min(size.width, size.height)); return .qr(l)
        case .unknown: return self
        }
    }

    init(from decoder: Decoder) throws {
        let probe = try decoder.container(keyedBy: TypeKey.self)
        let type = (try? probe.decode(String.self, forKey: .type)) ?? ""
        let single = try decoder.singleValueContainer()
        switch type {
        case "text": self = .text(try single.decode(TextLayer.self))
        case "image": self = .image(try single.decode(ImageLayer.self))
        case "sticker": self = .sticker(try single.decode(StickerLayer.self))
        case "shape": self = .shape(try single.decode(ShapeLayer.self))
        case "qr": self = .qr(try single.decode(QRLayer.self))
        default:
            let raw = try single.decode(JSONValue.self)
            let id = (try? probe.decode(String.self, forKey: .id)) ?? UUID().uuidString
            self = .unknown(id: id, raw: raw)
        }
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .text(let l): try container.encode(TypedLayer(type: "text", layer: l))
        case .image(let l): try container.encode(TypedLayer(type: "image", layer: l))
        case .sticker(let l): try container.encode(TypedLayer(type: "sticker", layer: l))
        case .shape(let l): try container.encode(TypedLayer(type: "shape", layer: l))
        case .qr(let l): try container.encode(TypedLayer(type: "qr", layer: l))
        case .unknown(_, let raw): try container.encode(raw)
        }
    }
}

/// `type` is a discriminator on the wire but not a field on the Swift structs,
/// so it is spliced back in at encode time.
private struct TypedLayer<T: Encodable>: Encodable {
    let type: String
    let layer: T

    private struct TypeOnly: Encodable { let type: String }

    func encode(to encoder: Encoder) throws {
        try layer.encode(to: encoder)
        try TypeOnly(type: type).encode(to: encoder)
    }
}

// MARK: - Document

struct FlyerDesign: Codable, Equatable {
    var version: Int
    var artboard: FlyerArtboard
    var background: FlyerBackground
    var palette: [String: String]?
    var layers: [DesignLayer]

    var backgroundColor: Color {
        resolveFlyerColor(background.color ?? "paper", palette: palette)
    }

    func index(of layerId: String) -> Int? {
        layers.firstIndex { $0.id == layerId }
    }

    /// Bounds-aware, matching utils/designer.ts:hasQrInBounds — a QR parked
    /// outside the artboard is clipped at render AND export, so counting it
    /// would report a flyer as scannable when nothing prints.
    var hasUsableQR: Bool {
        layers.contains { layer in
            guard case .qr = layer else { return false }
            let o = layer.origin, b = layer.box
            return o.x + b.width > 0 && o.y + b.height > 0
                && o.x < artboard.w && o.y < artboard.h
        }
    }
}
