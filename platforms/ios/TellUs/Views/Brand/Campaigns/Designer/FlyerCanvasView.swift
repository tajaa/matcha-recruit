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
    let onBeginTextEdit: (String) -> Void

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
            onLayerChange: onLayerChange,
            onBeginTextEdit: onBeginTextEdit
        )
    }
}

final class FlyerCanvasUIView: UIView, UIGestureRecognizerDelegate {
    private var design = FlyerDesignFactory.blank()
    private var claimURL = ""
    private var assets = FlyerRenderAssets.bundled
    private var selectedLayerID: String?
    private var interactive = true
    private var onSelect: ((String?) -> Void)?
    private var onLayerChange: ((DesignLayer, Bool) -> Void)?
    private var onBeginTextEdit: ((String) -> Void)?
    private var pan: UIPanGestureRecognizer!
    private var pinch: UIPinchGestureRecognizer!
    private var rotate: UIRotationGestureRecognizer!
    private var doubleTap: UITapGestureRecognizer!
    private var dragLayer: DesignLayer?
    private var dragStartOrigin: CGPoint = .zero
    private var didMove = false
    private var resizeLayer: DesignLayer?
    private var resizeHandle: FlyerResizeHandle?
    private var gestureBaseLayer: DesignLayer?

    override init(frame: CGRect) {
        super.init(frame: frame)
        backgroundColor = .secondarySystemBackground
        pan = UIPanGestureRecognizer(target: self, action: #selector(handlePan(_:)))
        pan.minimumNumberOfTouches = 1
        pan.maximumNumberOfTouches = 1
        addGestureRecognizer(pan)
        pinch = UIPinchGestureRecognizer(target: self, action: #selector(handlePinch(_:)))
        rotate = UIRotationGestureRecognizer(target: self, action: #selector(handleRotate(_:)))
        doubleTap = UITapGestureRecognizer(target: self, action: #selector(handleDoubleTap(_:)))
        doubleTap.numberOfTapsRequired = 2
        [pinch, rotate, doubleTap].forEach {
            $0.delegate = self
            addGestureRecognizer($0)
        }
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
        onLayerChange: @escaping (DesignLayer, Bool) -> Void,
        onBeginTextEdit: @escaping (String) -> Void
    ) {
        self.design = design
        self.claimURL = claimURL
        self.assets = assets
        self.selectedLayerID = selectedLayerID
        self.interactive = interactive
        self.onSelect = onSelect
        self.onLayerChange = onLayerChange
        self.onBeginTextEdit = onBeginTextEdit
        pan.isEnabled = interactive
        pinch.isEnabled = interactive
        rotate.isEnabled = interactive
        doubleTap.isEnabled = interactive
        setNeedsDisplay()
    }

    func gestureRecognizer(_ gestureRecognizer: UIGestureRecognizer, shouldRecognizeSimultaneouslyWith otherGestureRecognizer: UIGestureRecognizer) -> Bool {
        (gestureRecognizer === pinch && otherGestureRecognizer === rotate)
            || (gestureRecognizer === rotate && otherGestureRecognizer === pinch)
    }

    override func draw(_ rect: CGRect) {
        guard let context = UIGraphicsGetCurrentContext() else { return }
        let artboard = artboardRect(in: bounds)
        context.saveGState()
        context.translateBy(x: artboard.minX, y: artboard.minY)
        context.scaleBy(x: artboard.width / CGFloat(design.artboard.w), y: artboard.height / CGFloat(design.artboard.h))
        FlyerRenderer.draw(design: design, claimURL: claimURL, assets: assets, in: context)
        if let selectedLayerID, let layer = design.layers.first(where: { $0.id == selectedLayerID }), layer.kind != "unknown" {
            context.saveGState()
            context.translateBy(x: layer.origin.x, y: layer.origin.y)
            context.rotate(by: CGFloat(layer.rotation * .pi / 180))
            context.setStrokeColor(UIColor.systemOrange.cgColor)
            context.setLineWidth(4 / max(0.01, artboard.width / CGFloat(design.artboard.w)))
            context.setLineDash(phase: 0, lengths: [8, 5])
            let box = CGRect(origin: .zero, size: layer.box)
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
            context.restoreGState()
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
                didMove = false
                resizeLayer = nil
                return
            }
            if let handle = FlyerCanvasGeometry.resizeHandle(at: point, layer: layer) {
                resizeLayer = layer
                resizeHandle = handle
                dragLayer = nil
                didMove = false
                return
            }
            dragLayer = layer
            dragStartOrigin = layer.origin
            didMove = false
        case .changed, .ended:
            if let original = resizeLayer, let resizeHandle {
                let translation = recognizer.translation(in: self)
                didMove = didMove || hypot(translation.x, translation.y) > 1
                guard didMove else {
                    if recognizer.state == .ended {
                        self.resizeLayer = nil
                        self.resizeHandle = nil
                    }
                    return
                }
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
            didMove = didMove || hypot(translation.x, translation.y) > 1
            guard didMove else {
                if recognizer.state == .ended { dragLayer = nil }
                return
            }
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
            didMove = false
            resizeLayer = nil
            resizeHandle = nil
        }
    }

    @objc private func handlePinch(_ recognizer: UIPinchGestureRecognizer) {
        guard interactive, let id = selectedLayerID else { return }
        switch recognizer.state {
        case .began:
            gestureBaseLayer = design.layers.first { $0.id == id && !$0.isLocked }
        case .changed, .ended:
            guard let base = gestureBaseLayer else { return }
            let changed = FlyerCanvasGeometry.scaled(base, by: Double(recognizer.scale))
            onLayerChange?(changed, recognizer.state == .ended)
            if recognizer.state == .ended { gestureBaseLayer = nil }
        default:
            gestureBaseLayer = nil
        }
    }

    @objc private func handleRotate(_ recognizer: UIRotationGestureRecognizer) {
        guard interactive, let id = selectedLayerID else { return }
        switch recognizer.state {
        case .began:
            let candidate = design.layers.first { $0.id == id && !$0.isLocked }
            gestureBaseLayer = candidate?.kind == "qr" ? nil : candidate
        case .changed, .ended:
            guard let base = gestureBaseLayer else { return }
            let degrees = base.rotation + Double(recognizer.rotation) * 180 / .pi
            let changed = base.withRotation(FlyerCanvasGeometry.snapRotation(degrees: degrees))
            onLayerChange?(changed, recognizer.state == .ended)
            if recognizer.state == .ended { gestureBaseLayer = nil }
        default:
            gestureBaseLayer = nil
        }
    }

    @objc private func handleDoubleTap(_ recognizer: UITapGestureRecognizer) {
        guard interactive else { return }
        let point = pointInArtboard(recognizer.location(in: self))
        guard let id = FlyerCanvasGeometry.hitTest(at: point, in: design),
              let layer = design.layers.first(where: { $0.id == id }),
              case .text = layer else { return }
        onSelect?(id)
        onBeginTextEdit?(id)
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
