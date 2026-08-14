import SwiftUI
import UIKit

struct FlyerCanvasView: UIViewRepresentable {
    let design: FlyerDesign
    let claimURL: String
    let assets: FlyerRenderAssets
    let selectedLayerID: String?
    let interactive: Bool
    let onSelect: (String?) -> Void
    let onLayerChange: (DesignLayer, Bool) -> Void

    func makeUIView(context: Context) -> FlyerCanvasUIView {
        FlyerCanvasUIView()
    }

    func updateUIView(_ view: FlyerCanvasUIView, context: Context) {
        view.update(
            design: design,
            claimURL: claimURL,
            assets: assets,
            selectedLayerID: selectedLayerID,
            interactive: interactive,
            onSelect: onSelect,
            onLayerChange: onLayerChange
        )
    }
}

final class FlyerCanvasUIView: UIView {
    private var design = FlyerDesignFactory.blank()
    private var claimURL = ""
    private var assets = FlyerRenderAssets.bundled
    private var selectedLayerID: String?
    private var interactive = true
    private var onSelect: ((String?) -> Void)?
    private var onLayerChange: ((DesignLayer, Bool) -> Void)?
    private var pan: UIPanGestureRecognizer!
    private var dragLayer: DesignLayer?
    private var dragStartOrigin: CGPoint = .zero
    private var resizeLayer: DesignLayer?
    private var resizeHandle: FlyerResizeHandle?

    override init(frame: CGRect) {
        super.init(frame: frame)
        backgroundColor = .secondarySystemBackground
        pan = UIPanGestureRecognizer(target: self, action: #selector(handlePan(_:)))
        pan.minimumNumberOfTouches = 1
        pan.maximumNumberOfTouches = 1
        addGestureRecognizer(pan)
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    func update(
        design: FlyerDesign,
        claimURL: String,
        assets: FlyerRenderAssets,
        selectedLayerID: String?,
        interactive: Bool,
        onSelect: @escaping (String?) -> Void,
        onLayerChange: @escaping (DesignLayer, Bool) -> Void
    ) {
        self.design = design
        self.claimURL = claimURL
        self.assets = assets
        self.selectedLayerID = selectedLayerID
        self.interactive = interactive
        self.onSelect = onSelect
        self.onLayerChange = onLayerChange
        pan.isEnabled = interactive
        setNeedsDisplay()
    }

    override func draw(_ rect: CGRect) {
        guard let context = UIGraphicsGetCurrentContext() else { return }
        let artboard = artboardRect(in: bounds)
        context.saveGState()
        context.translateBy(x: artboard.minX, y: artboard.minY)
        context.scaleBy(x: artboard.width / CGFloat(design.artboard.w), y: artboard.height / CGFloat(design.artboard.h))
        FlyerRenderer.draw(design: design, claimURL: claimURL, assets: assets, in: context)
        if let selectedLayerID, let layer = design.layers.first(where: { $0.id == selectedLayerID }), layer.kind != "unknown" {
            context.setStrokeColor(UIColor.systemOrange.cgColor)
            context.setLineWidth(4 / max(0.01, artboard.width / CGFloat(design.artboard.w)))
            context.setLineDash(phase: 0, lengths: [8, 5])
            let box = CGRect(origin: layer.origin, size: layer.box)
            context.stroke(box)
            context.setFillColor(UIColor.systemOrange.cgColor)
            let handleSize = 18 / max(0.01, artboard.width / CGFloat(design.artboard.w))
            let corners = [
                CGPoint(x: box.minX, y: box.minY),
                CGPoint(x: box.maxX, y: box.minY),
                CGPoint(x: box.minX, y: box.maxY),
                CGPoint(x: box.maxX, y: box.maxY),
            ]
            for corner in corners {
                context.fillEllipse(in: CGRect(x: corner.x - handleSize / 2, y: corner.y - handleSize / 2, width: handleSize, height: handleSize))
            }
        }
        context.restoreGState()
    }

    @objc private func handlePan(_ recognizer: UIPanGestureRecognizer) {
        guard interactive else { return }
        let point = pointInArtboard(recognizer.location(in: self))
        switch recognizer.state {
        case .began:
            let id = FlyerCanvasGeometry.hitTest(at: point, in: design)
            onSelect?(id)
            guard let id, let layer = design.layers.first(where: { $0.id == id }), !layer.isLocked else {
                dragLayer = nil
                resizeLayer = nil
                return
            }
            if let handle = FlyerCanvasGeometry.resizeHandle(at: point, layer: layer) {
                resizeLayer = layer
                resizeHandle = handle
                dragLayer = nil
                return
            }
            dragLayer = layer
            dragStartOrigin = layer.origin
        case .changed, .ended:
            if let original = resizeLayer, let resizeHandle {
                let translation = recognizer.translation(in: self)
                let scale = artboardRect(in: bounds).width / CGFloat(design.artboard.w)
                let changed = FlyerCanvasGeometry.resized(
                    original,
                    handle: resizeHandle,
                    translation: CGSize(width: translation.x / max(0.01, scale), height: translation.y / max(0.01, scale))
                )
                onLayerChange?(changed, recognizer.state == .ended)
                if recognizer.state == .ended {
                    self.resizeLayer = nil
                    self.resizeHandle = nil
                }
                return
            }
            guard let original = dragLayer else { return }
            let translation = recognizer.translation(in: self)
            let scale = artboardRect(in: bounds).width / CGFloat(design.artboard.w)
            let proposed = CGPoint(
                x: dragStartOrigin.x + translation.x / max(0.01, scale),
                y: dragStartOrigin.y + translation.y / max(0.01, scale)
            )
            let snapped = FlyerCanvasGeometry.snap(layer: original, proposedOrigin: proposed, in: design)
            let changed = original.moved(to: snapped.origin)
            onLayerChange?(changed, recognizer.state == .ended)
            if recognizer.state == .ended { dragLayer = nil }
        default:
            dragLayer = nil
            resizeLayer = nil
            resizeHandle = nil
        }
    }

    private func artboardRect(in bounds: CGRect) -> CGRect {
        let padding: CGFloat = 24
        let available = bounds.insetBy(dx: padding, dy: padding)
        let scale = min(available.width / CGFloat(design.artboard.w), available.height / CGFloat(design.artboard.h))
        let size = CGSize(width: CGFloat(design.artboard.w) * scale, height: CGFloat(design.artboard.h) * scale)
        return CGRect(
            x: bounds.midX - size.width / 2,
            y: bounds.midY - size.height / 2,
            width: size.width,
            height: size.height
        )
    }

    private func pointInArtboard(_ point: CGPoint) -> CGPoint {
        let rect = artboardRect(in: bounds)
        return CGPoint(
            x: (point.x - rect.minX) / max(0.01, rect.width / CGFloat(design.artboard.w)),
            y: (point.y - rect.minY) / max(0.01, rect.height / CGFloat(design.artboard.h))
        )
    }
}
