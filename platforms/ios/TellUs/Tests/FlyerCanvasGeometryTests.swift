import CoreGraphics
import XCTest
@testable import TellUs

final class FlyerCanvasGeometryTests: XCTestCase {
    func testHitTestReturnsTopmostOverlappingLayer() {
        var design = FlyerDesignFactory.blank()
        let lower = FlyerDesignFactory.shape(in: design, shape: "rect").moved(to: CGPoint(x: 100, y: 100))
        let upper = FlyerDesignFactory.shape(in: design, shape: "rect").moved(to: CGPoint(x: 100, y: 100))
        design.layers = [lower, upper]

        XCTAssertEqual(FlyerCanvasGeometry.hitTest(at: CGPoint(x: 150, y: 150), in: design), upper.id)
    }

    func testHitTestAccountsForLayerRotation() {
        var design = FlyerDesignFactory.blank()
        let base = FlyerDesignFactory.shape(in: design, shape: "rect")
        let rotated = base.withRotation(45).moved(to: CGPoint(x: 100, y: 100))
        design.layers = [rotated]

        XCTAssertEqual(FlyerCanvasGeometry.hitTest(at: CGPoint(x: 120, y: 120), in: design), rotated.id)
        XCTAssertNil(FlyerCanvasGeometry.hitTest(at: CGPoint(x: 0, y: 0), in: design))
    }

    func testSnapUsesArtboardCenterAndNeighborEdges() {
        var design = FlyerDesignFactory.blank()
        let fixed = FlyerDesignFactory.shape(in: design, shape: "rect").moved(to: CGPoint(x: 100, y: 100))
        let moving = FlyerDesignFactory.shape(in: design, shape: "rect").moved(to: CGPoint(x: 500, y: 500))
        design.layers = [fixed, moving]

        let neighbor = FlyerCanvasGeometry.snap(
            layer: moving,
            proposedOrigin: CGPoint(x: 100 + moving.box.width + 5, y: 500),
            in: design
        )
        XCTAssertEqual(neighbor.origin.x, 100 + moving.box.width, accuracy: 0.01)
        XCTAssertTrue(neighbor.verticalGuides.contains(100 + fixed.box.width))

        let center = FlyerCanvasGeometry.snap(
            layer: moving,
            proposedOrigin: CGPoint(x: 637.5 - moving.box.width / 2, y: 800),
            in: design
        )
        XCTAssertEqual(center.origin.x + moving.box.width / 2, 637.5, accuracy: 8)
        XCTAssertTrue(center.verticalGuides.contains(637.5))
    }

    func testUnknownLayersAreNotHitTestTargetsAndLockedLayersRemainSelectable() {
        var design = FlyerDesignFactory.blank()
        let locked = FlyerDesignFactory.shape(in: design, shape: "rect").withLock(true)
        let unknown = DesignLayer.unknown(id: "video", raw: .object(["type": .string("video")]))
        design.layers = [locked, unknown]

        XCTAssertEqual(FlyerCanvasGeometry.hitTest(at: locked.origin, in: design), locked.id)
        XCTAssertNil(FlyerCanvasGeometry.hitTest(at: CGPoint(x: 1, y: 1), in: design))
    }

    func testResizeHandleChangesTextWidthAndKeepsImageAspectRatio() {
        let design = FlyerDesignFactory.blank()
        let text = FlyerDesignFactory.text(in: design, text: "Headline")
        let resizedText = FlyerCanvasGeometry.resized(
            text,
            handle: .bottomRight,
            translation: CGSize(width: 100, height: 20)
        )
        XCTAssertEqual(resizedText.box.width, text.box.width + 100, accuracy: 0.01)

        let image = FlyerDesignFactory.image(in: design, source: "https://example.com/image.png", size: CGSize(width: 200, height: 100))
        let resizedImage = FlyerCanvasGeometry.resized(
            image,
            handle: .bottomRight,
            translation: CGSize(width: 100, height: 0)
        )
        XCTAssertEqual(resizedImage.box.width / resizedImage.box.height, 2, accuracy: 0.01)
    }

    func testResizeHandleAccountsForLayerRotation() {
        let design = FlyerDesignFactory.blank()
        let layer = FlyerDesignFactory.shape(in: design, shape: "rect").withRotation(45).moved(to: CGPoint(x: 100, y: 100))
        let angle = CGFloat(45 * Double.pi / 180)
        let corner = CGPoint(
            x: layer.origin.x + layer.box.width * cos(angle),
            y: layer.origin.y + layer.box.width * sin(angle)
        )

        XCTAssertEqual(FlyerCanvasGeometry.resizeHandle(at: corner, layer: layer), .topRight)
    }

    func testScaledKeepsLayerCentre() {
        let layer = FlyerDesignFactory.sticker(in: FlyerDesignFactory.blank(), assetID: "star", size: CGSize(width: 120, height: 80))
        let before = CGPoint(x: layer.origin.x + layer.box.width / 2, y: layer.origin.y + layer.box.height / 2)

        for factor in [2.0, 0.5] {
            let scaled = FlyerCanvasGeometry.scaled(layer, by: factor)
            let after = CGPoint(x: scaled.origin.x + scaled.box.width / 2, y: scaled.origin.y + scaled.box.height / 2)
            XCTAssertEqual(after.x, before.x, accuracy: 0.01)
            XCTAssertEqual(after.y, before.y, accuracy: 0.01)
        }
    }

    func testScaledClampsToUpperAndLowerBounds() {
        let layer = FlyerDesignFactory.sticker(in: FlyerDesignFactory.blank(), assetID: "star", size: CGSize(width: 120, height: 80))

        XCTAssertLessThanOrEqual(FlyerCanvasGeometry.scaled(layer, by: 100).box.width, 4000)
        XCTAssertGreaterThanOrEqual(FlyerCanvasGeometry.scaled(layer, by: 0.001).box.width, 8)
    }

    func testScaledTextScalesFontSizeAndWidthTogether() {
        let text = FlyerDesignFactory.text(in: FlyerDesignFactory.blank(), text: "Headline")
        let scaled = FlyerCanvasGeometry.scaled(text, by: 2)

        guard case .text(let original) = text, case .text(let result) = scaled else {
            return XCTFail("Expected text layers")
        }
        XCTAssertEqual(result.width / original.width, result.fontSize / original.fontSize, accuracy: 0.01)
    }

    func testScaledQRStaysSquare() {
        let qr = FlyerDesignFactory.qr(in: FlyerDesignFactory.blank())
        let scaled = FlyerCanvasGeometry.scaled(qr, by: 2)

        XCTAssertEqual(scaled.box.width, scaled.box.height, accuracy: 0.01)
    }

    func testSnapRotationSnapsNearRightAngles() {
        XCTAssertEqual(FlyerCanvasGeometry.snapRotation(degrees: 88), 90)
        XCTAssertEqual(FlyerCanvasGeometry.snapRotation(degrees: 3), 0)
        XCTAssertEqual(FlyerCanvasGeometry.snapRotation(degrees: 45), 45)
    }

    func testSnapRotationNormalisesBeyond180() {
        XCTAssertEqual(FlyerCanvasGeometry.snapRotation(degrees: 200), -160)
    }

    func testWithSizeRejectsOutOfRangeForServer() {
        let design = FlyerDesignFactory.blank()
        let layers: [DesignLayer] = [
            FlyerDesignFactory.text(in: design, text: "Text").withSize(width: 99999, height: 99999),
            FlyerDesignFactory.image(in: design, source: "image", size: CGSize(width: 100, height: 100)).withSize(width: 99999, height: 99999),
            FlyerDesignFactory.sticker(in: design, assetID: "star").withSize(width: 99999, height: 99999),
            FlyerDesignFactory.shape(in: design, shape: "rect").withSize(width: 99999, height: 99999),
            FlyerDesignFactory.qr(in: design).withSize(width: 99999),
        ]

        for layer in layers {
            XCTAssertLessThanOrEqual(layer.box.width, 4000)
            XCTAssertLessThanOrEqual(layer.box.height, 4000)
        }
    }
}
