import CoreGraphics

struct FlyerSnapResult: Equatable {
    let origin: CGPoint
    let verticalGuides: [CGFloat]
    let horizontalGuides: [CGFloat]
}

enum FlyerResizeHandle: CaseIterable {
    case topLeft
    case topRight
    case bottomLeft
    case bottomRight
}

enum FlyerCanvasGeometry {
    static func hitTest(at point: CGPoint, in design: FlyerDesign) -> String? {
        for layer in design.layers.reversed() {
            guard layer.kind != "unknown" else { continue }
            let box = layer.box
            let local = rotatedPoint(point, around: layer.origin, radians: -layer.rotation * .pi / 180)
            let rect = CGRect(origin: layer.origin, size: box)
            if rect.contains(local) { return layer.id }
        }
        return nil
    }

    static func snap(
        layer: DesignLayer,
        proposedOrigin: CGPoint,
        in design: FlyerDesign,
        threshold: CGFloat = 8
    ) -> FlyerSnapResult {
        let box = layer.box
        var vertical = [CGFloat(0), CGFloat(design.artboard.w) / 2, CGFloat(design.artboard.w)]
        var horizontal = [CGFloat(0), CGFloat(design.artboard.h) / 2, CGFloat(design.artboard.h)]
        for other in design.layers where other.id != layer.id && other.kind != "unknown" {
            let otherBox = other.box
            vertical += [other.origin.x, other.origin.x + otherBox.width / 2, other.origin.x + otherBox.width]
            horizontal += [other.origin.y, other.origin.y + otherBox.height / 2, other.origin.y + otherBox.height]
        }

        var x = proposedOrigin.x
        var y = proposedOrigin.y
        var verticalHits: [CGFloat] = []
        var horizontalHits: [CGFloat] = []
        for guide in vertical {
            for (edge, offset) in [(x, CGFloat(0)), (x + box.width / 2, box.width / 2), (x + box.width, box.width)] {
                if abs(edge - guide) <= threshold {
                    x = guide - offset
                    verticalHits.append(guide)
                }
            }
        }
        for guide in horizontal {
            for (edge, offset) in [(y, CGFloat(0)), (y + box.height / 2, box.height / 2), (y + box.height, box.height)] {
                if abs(edge - guide) <= threshold {
                    y = guide - offset
                    horizontalHits.append(guide)
                }
            }
        }
        return FlyerSnapResult(
            origin: CGPoint(x: x.rounded(), y: y.rounded()),
            verticalGuides: Array(Set(verticalHits)).sorted(),
            horizontalGuides: Array(Set(horizontalHits)).sorted()
        )
    }

    static func resizeHandle(at point: CGPoint, layer: DesignLayer, tolerance: CGFloat = 24) -> FlyerResizeHandle? {
        guard layer.kind != "unknown", !layer.isLocked else { return nil }
        let origin = layer.origin
        let box = layer.box
        let localPoint = rotatedPoint(point, around: origin, radians: -layer.rotation * .pi / 180)
        let corners: [(FlyerResizeHandle, CGPoint)] = [
            (.topLeft, origin),
            (.topRight, CGPoint(x: origin.x + box.width, y: origin.y)),
            (.bottomLeft, CGPoint(x: origin.x, y: origin.y + box.height)),
            (.bottomRight, CGPoint(x: origin.x + box.width, y: origin.y + box.height)),
        ]
        return corners.first { _, corner in abs(localPoint.x - corner.x) <= tolerance && abs(localPoint.y - corner.y) <= tolerance }?.0
    }

    static func resized(
        _ layer: DesignLayer,
        handle: FlyerResizeHandle,
        translation: CGSize
    ) -> DesignLayer {
        let box = layer.box
        var x = layer.origin.x
        var y = layer.origin.y
        var width = box.width
        var height = box.height
        switch handle {
        case .topLeft:
            x += translation.width
            y += translation.height
            width -= translation.width
            height -= translation.height
        case .topRight:
            y += translation.height
            width += translation.width
            height -= translation.height
        case .bottomLeft:
            x += translation.width
            width -= translation.width
            height += translation.height
        case .bottomRight:
            width += translation.width
            height += translation.height
        }

        if layer.kind == "qr" || layer.kind == "image" || layer.kind == "sticker" {
            let aspect = max(0.01, box.width / max(0.01, box.height))
            if abs(translation.width) >= abs(translation.height) {
                height = width / aspect
            } else {
                width = height * aspect
            }
            if handle == .topLeft || handle == .bottomLeft { x = layer.origin.x + box.width - width }
            if handle == .topLeft || handle == .topRight { y = layer.origin.y + box.height - height }
        }
        let moved = layer.moved(to: CGPoint(x: x, y: y))
        return moved.withSize(width: width, height: height)
    }

    /// Scale around the layer centre so a pinch does not make the layer jump.
    static func scaled(_ layer: DesignLayer, by factor: Double) -> DesignLayer {
        guard layer.kind != "unknown", factor.isFinite, factor > 0 else { return layer }
        let center = CGPoint(x: layer.origin.x + layer.box.width / 2, y: layer.origin.y + layer.box.height / 2)
        let scale = CGFloat(factor)
        let size: CGSize
        if layer.kind == "qr" {
            let side = min(FlyerLayerLimits.qrSize.upperBound, max(FlyerLayerLimits.qrSize.lowerBound, Double(layer.box.width) * factor))
            size = CGSize(width: CGFloat(side), height: CGFloat(side))
        } else {
            size = CGSize(width: layer.box.width * scale, height: layer.box.height * scale)
        }
        let changed = layer.resized(to: size)
        return changed.moved(to: CGPoint(x: center.x - changed.box.width / 2, y: center.y - changed.box.height / 2))
    }

    static func snapRotation(degrees: Double, detent: Double = 6) -> Double {
        guard degrees.isFinite, detent >= 0 else { return 0 }
        var normalized = degrees.truncatingRemainder(dividingBy: 360)
        if normalized > 180 { normalized -= 360 }
        if normalized < -180 { normalized += 360 }
        for target in [0.0, 90.0, -90.0, 180.0, -180.0] where abs(normalized - target) <= detent {
            return target == -180 ? 180 : target
        }
        return normalized
    }

    private static func rotatedPoint(_ point: CGPoint, around origin: CGPoint, radians: CGFloat) -> CGPoint {
        let dx = point.x - origin.x
        let dy = point.y - origin.y
        return CGPoint(
            x: origin.x + dx * cos(radians) - dy * sin(radians),
            y: origin.y + dx * sin(radians) + dy * cos(radians)
        )
    }
}
