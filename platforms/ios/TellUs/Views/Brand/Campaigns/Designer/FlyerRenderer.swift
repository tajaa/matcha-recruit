import CoreImage
import CoreImage.CIFilterBuiltins
import CoreText
import UIKit

enum FlyerRenderer {
    static func draw(
        design: FlyerDesign,
        claimURL: String?,
        assets: FlyerRenderAssets,
        in context: CGContext
    ) {
        let width = CGFloat(design.artboard.w)
        let height = CGFloat(design.artboard.h)
        context.saveGState()
        context.setFillColor(color(design.background.color ?? "paper", palette: design.palette).cgColor)
        context.fill(CGRect(x: 0, y: 0, width: width, height: height))

        for layer in design.layers {
            draw(layer: layer, design: design, claimURL: claimURL, assets: assets, in: context)
        }
        context.restoreGState()
    }

    static func image(
        design: FlyerDesign,
        claimURL: String,
        assets: FlyerRenderAssets,
        pixelMultiplier: CGFloat
    ) throws -> UIImage {
        let width = CGFloat(design.artboard.w) * pixelMultiplier
        let height = CGFloat(design.artboard.h) * pixelMultiplier
        let format = UIGraphicsImageRendererFormat()
        format.scale = 1
        format.opaque = true
        let renderer = UIGraphicsImageRenderer(size: CGSize(width: width, height: height), format: format)
        return renderer.image { imageContext in
            imageContext.cgContext.scaleBy(x: pixelMultiplier, y: pixelMultiplier)
            draw(design: design, claimURL: claimURL, assets: assets, in: imageContext.cgContext)
        }
    }

    private static func draw(
        layer: DesignLayer,
        design: FlyerDesign,
        claimURL: String?,
        assets: FlyerRenderAssets,
        in context: CGContext
    ) {
        guard layer.kind != "unknown" else { return }
        context.saveGState()
        context.translateBy(x: layer.origin.x, y: layer.origin.y)
        context.rotate(by: CGFloat(layer.rotation * .pi / 180))
        context.setAlpha(CGFloat(layer.opacity))

        switch layer {
        case .text(let text): draw(text, palette: design.palette, in: context)
        case .image(let image): draw(image, assets: assets, in: context)
        case .sticker(let sticker): draw(sticker, assets: assets, in: context)
        case .shape(let shape): draw(shape, palette: design.palette, in: context)
        case .qr(let qr): draw(qr, palette: design.palette, claimURL: claimURL, in: context)
        case .unknown: break
        }
        context.restoreGState()
    }

    private static func draw(_ layer: TextLayer, palette: [String: String]?, in context: CGContext) {
        let paragraph = NSMutableParagraphStyle()
        paragraph.alignment = {
            switch layer.align {
            case "right": return .right
            case "center": return .center
            default: return .left
            }
        }()
        paragraph.lineBreakMode = .byWordWrapping
        paragraph.lineSpacing = CGFloat(max(0, layer.fontSize * (layer.lineHeight - 1)))
        let font = UIFont(name: flyerFontName(layer.fontFamily), size: CGFloat(layer.fontSize))
            ?? UIFont.systemFont(ofSize: CGFloat(layer.fontSize), weight: layer.fontStyle == "bold" ? .bold : .regular)
        let traits: UIFontDescriptor.SymbolicTraits = layer.fontStyle == "italic" ? .traitItalic : []
        let styledFont = traits.isEmpty ? font : UIFont(descriptor: font.fontDescriptor.withSymbolicTraits(traits) ?? font.fontDescriptor, size: font.pointSize)
        let attributes: [NSAttributedString.Key: Any] = [
            .font: styledFont,
            .foregroundColor: color(layer.fill, palette: palette),
            .paragraphStyle: paragraph,
            .kern: CGFloat(layer.letterSpacing),
        ]
        NSString(string: layer.text).draw(
            in: CGRect(x: 0, y: 0, width: CGFloat(layer.width), height: layer.measuredHeight),
            withAttributes: attributes
        )
    }

    private static func draw(_ layer: ImageLayer, assets: FlyerRenderAssets, in context: CGContext) {
        let image = layer.slot == "logo" ? assets.logo : assets.images[layer.src]
        guard let cgImage = image?.cgImage else { return }
        context.interpolationQuality = .high
        context.draw(cgImage, in: CGRect(x: 0, y: 0, width: layer.width, height: layer.height))
    }

    private static func draw(_ layer: StickerLayer, assets: FlyerRenderAssets, in context: CGContext) {
        guard let image = assets.stickers[layer.assetId], let cgImage = image.cgImage else { return }
        context.interpolationQuality = .high
        context.draw(cgImage, in: CGRect(x: 0, y: 0, width: layer.width, height: layer.height))
    }

    private static func draw(_ layer: ShapeLayer, palette: [String: String]?, in context: CGContext) {
        let rect = CGRect(x: 0, y: 0, width: layer.width, height: layer.height)
        let fill = color(layer.fill, palette: palette).cgColor
        switch layer.shape {
        case "circle":
            context.setFillColor(fill)
            context.fillEllipse(in: rect)
        case "line":
            context.setStrokeColor(color(layer.stroke ?? layer.fill, palette: palette).cgColor)
            context.setLineWidth(CGFloat(layer.height))
            context.setLineCap(.round)
            context.move(to: CGPoint(x: 0, y: 0))
            context.addLine(to: CGPoint(x: layer.width, y: 0))
            context.strokePath()
        default:
            let path = CGPath(roundedRect: rect, cornerWidth: CGFloat(layer.cornerRadius ?? 0), cornerHeight: CGFloat(layer.cornerRadius ?? 0), transform: nil)
            context.addPath(path)
            context.setFillColor(fill)
            context.fillPath()
            if let stroke = layer.stroke {
                context.addPath(path)
                context.setStrokeColor(color(stroke, palette: palette).cgColor)
                context.setLineWidth(CGFloat(layer.strokeWidth ?? 1))
                context.strokePath()
            }
        }
    }

    private static func draw(_ layer: QRLayer, palette: [String: String]?, claimURL: String?, in context: CGContext) {
        let rect = CGRect(x: 0, y: 0, width: layer.size, height: layer.size)
        let fg = color(layer.fg, palette: palette)
        let bg = color(layer.bg, palette: palette)
        context.setFillColor(bg.cgColor)
        context.fill(rect)
        guard let claimURL, let image = qrImage(value: claimURL, foreground: fg, background: bg), let cgImage = image.cgImage else {
            context.setStrokeColor(fg.cgColor)
            context.setLineWidth(max(2, layer.size * 0.02))
            context.setLineDash(phase: 0, lengths: [layer.size * 0.08, layer.size * 0.06])
            context.stroke(rect.insetBy(dx: layer.size * 0.02, dy: layer.size * 0.02))
            return
        }
        context.interpolationQuality = .none
        context.draw(cgImage, in: rect)
    }

    private static func qrImage(value: String, foreground: UIColor, background: UIColor) -> UIImage? {
        let generator = CIFilter.qrCodeGenerator()
        generator.message = Data(value.utf8)
        generator.correctionLevel = "M"
        guard let qr = generator.outputImage else { return nil }
        let falseColor = CIFilter.falseColor()
        falseColor.inputImage = qr
        falseColor.color0 = CIColor(color: foreground)
        falseColor.color1 = CIColor(color: background)
        guard let output = falseColor.outputImage else { return nil }
        let scale = 4.0
        let scaled = output.transformed(by: CGAffineTransform(scaleX: scale, y: scale))
        let context = CIContext()
        guard let image = context.createCGImage(scaled, from: scaled.extent) else { return nil }
        return UIImage(cgImage: image)
    }

    private static func color(_ value: String, palette: [String: String]?) -> UIColor {
        let swiftColor = resolveFlyerColor(value, palette: palette)
        return UIColor(swiftColor)
    }
}
