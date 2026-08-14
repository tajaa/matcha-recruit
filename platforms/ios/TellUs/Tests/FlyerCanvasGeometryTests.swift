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
}
