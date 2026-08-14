import Foundation

struct FlyerArtboardPreset: Equatable {
    let preset: String
    let w: Double
    let h: Double
    let label: String
}

enum FlyerArtboardPresets {
    static let all: [FlyerArtboardPreset] = [
        FlyerArtboardPreset(preset: "flyer_letter", w: 1275, h: 1650, label: "Flyer - US Letter"),
        FlyerArtboardPreset(preset: "reward_card", w: 1050, h: 600, label: "Reward card"),
        FlyerArtboardPreset(preset: "social_square", w: 1080, h: 1080, label: "Social square"),
        FlyerArtboardPreset(preset: "story", w: 1080, h: 1920, label: "Story"),
    ]

    static func spec(for preset: String) -> FlyerArtboardPreset? {
        all.first { $0.preset == preset }
    }
}

enum FlyerLayerDirection {
    case forward
    case backward
}

enum FlyerDesignFactory {
    static func blank(preset: String = "flyer_letter") -> FlyerDesign {
        let spec = FlyerArtboardPresets.spec(for: preset) ?? FlyerArtboardPresets.all[0]
        return FlyerDesign(
            version: 1,
            artboard: FlyerArtboard(preset: spec.preset, w: spec.w, h: spec.h),
            background: FlyerBackground(kind: "color", color: "paper", src: nil, fit: nil),
            palette: nil,
            layers: []
        )
    }

    static func text(in design: FlyerDesign, text: String) -> DesignLayer {
        let width = (design.artboard.w * 0.7).rounded()
        return .text(TextLayer(
            id: UUID().uuidString,
            x: ((design.artboard.w - width) / 2).rounded(),
            y: (design.artboard.h * 0.4).rounded(),
            rotation: 0,
            opacity: 1,
            locked: nil,
            text: text,
            fontFamily: "Helvetica Neue",
            fontSize: (design.artboard.h * 0.05).rounded(),
            fontStyle: "bold",
            fill: "ink",
            align: "center",
            width: width,
            lineHeight: 1.2,
            letterSpacing: 0
        ))
    }

    static func shape(in design: FlyerDesign, shape: String) -> DesignLayer {
        let size = min(design.artboard.w, design.artboard.h) * 0.25
        return .shape(ShapeLayer(
            id: UUID().uuidString,
            x: ((design.artboard.w - size) / 2).rounded(),
            y: ((design.artboard.h - size) / 2).rounded(),
            rotation: 0,
            opacity: 1,
            locked: nil,
            shape: ["rect", "circle", "line"].contains(shape) ? shape : "rect",
            width: size.rounded(),
            height: (shape == "line" ? 8 : size).rounded(),
            fill: "brand",
            stroke: nil,
            strokeWidth: nil,
            cornerRadius: shape == "rect" ? 16 : 0
        ))
    }

    static func sticker(in design: FlyerDesign, assetID: String, size: CGSize = CGSize(width: 200, height: 200)) -> DesignLayer {
        let scale = min(1, (design.artboard.w * 0.3) / max(1, size.width))
        let width = (size.width * scale).rounded()
        let height = (size.height * scale).rounded()
        return .sticker(StickerLayer(
            id: UUID().uuidString,
            x: ((design.artboard.w - width) / 2).rounded(),
            y: ((design.artboard.h - height) / 2).rounded(),
            rotation: 0,
            opacity: 1,
            locked: nil,
            assetId: assetID,
            width: width,
            height: height
        ))
    }

    static func image(in design: FlyerDesign, source: String, size: CGSize, slot: String? = nil) -> DesignLayer {
        let target = design.artboard.w * (slot == "logo" ? 0.25 : 0.5)
        let scale = target / max(1, size.width)
        let width = (size.width * scale).rounded()
        let height = (size.height * scale).rounded()
        return .image(ImageLayer(
            id: UUID().uuidString,
            x: ((design.artboard.w - width) / 2).rounded(),
            y: slot == "logo" ? (design.artboard.h * 0.06).rounded() : ((design.artboard.h - height) / 2).rounded(),
            rotation: 0,
            opacity: 1,
            locked: nil,
            src: source,
            width: width,
            height: height,
            slot: slot
        ))
    }

    static func qr(in design: FlyerDesign) -> DesignLayer {
        let size = (design.artboard.w * 0.32).rounded()
        return .qr(QRLayer(
            id: UUID().uuidString,
            x: ((design.artboard.w - size) / 2).rounded(),
            y: (design.artboard.h - size - design.artboard.h * 0.08).rounded(),
            rotation: 0,
            opacity: 1,
            locked: nil,
            size: size,
            fg: "#17140f",
            bg: "#ffffff"
        ))
    }

    static func starter(campaign: PromoCampaign, logoURL: String?) -> FlyerDesign {
        let base = blank()
        var layers: [DesignLayer] = []
        if let logoURL {
            layers.append(image(in: base, source: logoURL, size: CGSize(width: 512, height: 512), slot: "logo"))
        }
        layers.append(text(in: base, text: campaign.title).replacing(y: (base.artboard.h * 0.28).rounded(), fontSize: 96))
        layers.append(text(in: base, text: campaign.reward_text).replacing(
            y: (base.artboard.h * 0.44).rounded(), fontSize: 52, fontStyle: "normal", fill: "ink"
        ))
        layers.append(text(in: base, text: "Scan to claim").replacing(
            y: (base.artboard.h * 0.58).rounded(), fontSize: 34, fontStyle: "normal", fill: "muted"
        ))
        layers.append(qr(in: base))
        return FlyerDesign(version: base.version, artboard: base.artboard, background: base.background, palette: base.palette, layers: layers)
    }

    static func instantiate(_ template: FlyerDesign, logoURL: String?) -> FlyerDesign {
        let layers = template.layers.compactMap { layer -> DesignLayer? in
            switch layer {
            case .image(var image) where image.slot == "logo":
                guard let logoURL else { return nil }
                image.id = UUID().uuidString
                image.src = logoURL
                return .image(image)
            case .text(var text): text.id = UUID().uuidString; return .text(text)
            case .image(var image): image.id = UUID().uuidString; return .image(image)
            case .sticker(var sticker): sticker.id = UUID().uuidString; return .sticker(sticker)
            case .shape(var shape): shape.id = UUID().uuidString; return .shape(shape)
            case .qr(var qr): qr.id = UUID().uuidString; return .qr(qr)
            case .unknown(_, let raw):
                let id = UUID().uuidString
                guard var object = raw.objectValue else { return .unknown(id: id, raw: raw) }
                object["id"] = .string(id)
                return .unknown(id: id, raw: .object(object))
            }
        }
        return FlyerDesign(
            version: 1,
            artboard: template.artboard,
            background: template.background,
            palette: template.palette,
            layers: layers
        )
    }
}

extension DesignLayer {
    func replacing(
        x: Double? = nil,
        y: Double? = nil,
        fontSize: Double? = nil,
        fontStyle: String? = nil,
        fill: String? = nil
    ) -> DesignLayer {
        switch self {
        case .text(var layer):
            if let x { layer.x = x }
            if let y { layer.y = y }
            if let fontSize { layer.fontSize = fontSize }
            if let fontStyle { layer.fontStyle = fontStyle }
            if let fill { layer.fill = fill }
            return .text(layer)
        default:
            return self
        }
    }

    func withRotation(_ value: Double) -> DesignLayer {
        switch self {
        case .text(var layer): layer.rotation = value; return .text(layer)
        case .image(var layer): layer.rotation = value; return .image(layer)
        case .sticker(var layer): layer.rotation = value; return .sticker(layer)
        case .shape(var layer): layer.rotation = value; return .shape(layer)
        case .qr: return self
        case .unknown: return self
        }
    }

    func withLock(_ value: Bool) -> DesignLayer {
        switch self {
        case .text(var layer): layer.locked = value; return .text(layer)
        case .image(var layer): layer.locked = value; return .image(layer)
        case .sticker(var layer): layer.locked = value; return .sticker(layer)
        case .shape(var layer): layer.locked = value; return .shape(layer)
        case .qr(var layer): layer.locked = value; return .qr(layer)
        case .unknown: return self
        }
    }

    func withOpacity(_ value: Double) -> DesignLayer {
        let opacity = min(1, max(0.05, value))
        switch self {
        case .text(var layer): layer.opacity = opacity; return .text(layer)
        case .image(var layer): layer.opacity = opacity; return .image(layer)
        case .sticker(var layer): layer.opacity = opacity; return .sticker(layer)
        case .shape(var layer): layer.opacity = opacity; return .shape(layer)
        case .qr(var layer): layer.opacity = opacity; return .qr(layer)
        case .unknown: return self
        }
    }

    func withSize(width: Double, height: Double? = nil) -> DesignLayer {
        switch self {
        case .text(var layer):
            layer.width = max(24, width)
            if let height { layer.fontSize = max(8, height / max(0.7, layer.lineHeight)) }
            return .text(layer)
        case .image(var layer):
            layer.width = max(8, width)
            if let height { layer.height = max(8, height) }
            return .image(layer)
        case .sticker(var layer):
            layer.width = max(8, width)
            if let height { layer.height = max(8, height) }
            return .sticker(layer)
        case .shape(var layer):
            layer.width = max(4, width)
            if let height { layer.height = max(2, height) }
            return .shape(layer)
        case .qr(var layer):
            layer.size = max(96, width)
            return .qr(layer)
        case .unknown: return self
        }
    }

    func withFont(family: String) -> DesignLayer {
        guard case .text(var layer) = self else { return self }
        layer.fontFamily = family
        return .text(layer)
    }
}

extension FlyerDesign {
    func replacingLayer(_ replacement: DesignLayer) -> FlyerDesign {
        var copy = self
        guard let index = copy.index(of: replacement.id) else { return copy }
        copy.layers[index] = replacement
        return copy
    }

    func removingLayer(id: String) -> FlyerDesign {
        var copy = self
        copy.layers.removeAll { $0.id == id }
        return copy
    }

    func duplicatingLayer(id: String) -> FlyerDesign {
        guard let source = layers.first(where: { $0.id == id }) else { return self }
        let copy = source.withNewID().moved(to: CGPoint(x: source.origin.x + 24, y: source.origin.y + 24))
        var result = self
        result.layers.append(copy)
        return result
    }

    func reorderingLayer(id: String, direction: FlyerLayerDirection) -> FlyerDesign {
        guard let index = layers.firstIndex(where: { $0.id == id }) else { return self }
        let target = direction == .forward ? index + 1 : index - 1
        guard layers.indices.contains(target) else { return self }
        var copy = self
        copy.layers.swapAt(index, target)
        return copy
    }

    func retargeted(to preset: String) -> FlyerDesign {
        guard let spec = FlyerArtboardPresets.spec(for: preset) else { return self }
        let oldW = artboard.w
        let oldH = artboard.h
        guard oldW != spec.w || oldH != spec.h else {
            var copy = self
            copy.artboard = FlyerArtboard(preset: spec.preset, w: spec.w, h: spec.h)
            return copy
        }

        let sx = spec.w / oldW
        let sy = spec.h / oldH
        let scale = min(sx, sy)
        let layers = layers.map { layer -> DesignLayer in
            guard layer.kind != "unknown" else { return layer }
            let moved = layer.moved(to: CGPoint(x: layer.origin.x * sx, y: layer.origin.y * sy))
            let resized = moved.resized(to: CGSize(width: moved.box.width * scale, height: moved.box.height * scale))
            return resized.clamped(toWidth: spec.w, height: spec.h)
        }
        return FlyerDesign(
            version: version,
            artboard: FlyerArtboard(preset: spec.preset, w: spec.w, h: spec.h),
            background: background,
            palette: palette,
            layers: layers
        )
    }
}

private extension DesignLayer {
    func withNewID() -> DesignLayer {
        let id = UUID().uuidString
        switch self {
        case .text(var layer): layer.id = id; return .text(layer)
        case .image(var layer): layer.id = id; return .image(layer)
        case .sticker(var layer): layer.id = id; return .sticker(layer)
        case .shape(var layer): layer.id = id; return .shape(layer)
        case .qr(var layer): layer.id = id; return .qr(layer)
        case .unknown(_, let raw):
            guard var object = raw.objectValue else { return .unknown(id: id, raw: raw) }
            object["id"] = .string(id)
            return .unknown(id: id, raw: .object(object))
        }
    }

    func clamped(toWidth width: Double, height: Double) -> DesignLayer {
        let box = box
        let x = min(max(origin.x, 0), max(0, width - box.width)).rounded()
        let y = min(max(origin.y, 0), max(0, height - box.height)).rounded()
        return moved(to: CGPoint(x: x, y: y))
    }
}
