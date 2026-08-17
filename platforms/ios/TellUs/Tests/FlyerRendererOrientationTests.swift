import UIKit
import XCTest
@testable import TellUs

/// Pins the flip fix in FlyerRenderer.swift (drawUpright). Confirmed
/// empirically (not just from the classic "CGContextDrawImage in drawRect:
/// is upside-down" folklore, which turned out NOT to reproduce for a plain
/// UIKit-decoded PNG/JPEG in this renderer's contexts) that the flip is
/// needed for exactly two of the three raster layer kinds:
///   - stickers: Xcode's SVG-asset-catalog compiler bakes a y-up bitmap
///   - QR: CoreImage's CIContext.createCGImage output is natively y-up
/// and must NOT be applied to the `image`/logo layer, whose UIImage always
/// comes from ImageIO-decoded PNG/JPEG bytes (already top-down) — applying
/// the flip there re-inverts an already-correct image.
final class FlyerRendererOrientationTests: XCTestCase {
    func testStickerLayerRendersUpright() throws {
        // Real sticker-coffee-cup.svg (200x200 viewBox): a filled black
        // saucer rect sits at y=176-188 (near the BOTTOM edge, spanning most
        // of the width) while the cup body sits mid-upper. Placed at the
        // design origin with matching size, its output should show more
        // dark mass in the bottom half of that 200x200 region than the top.
        var design = FlyerDesignFactory.blank()
        let layer = FlyerDesignFactory.sticker(in: design, assetID: "coffee-cup.svg", size: CGSize(width: 200, height: 200))
        design.layers = [repositioned(layer, x: 0, y: 0)]

        let rendered = try FlyerRenderer.image(
            design: design, claimURL: "https://example.com/promo/claim",
            assets: .bundled, pixelMultiplier: 1
        )

        let (topDark, bottomDark) = darkMassSplit(of: rendered, regionSize: 200, darkThreshold: 128)
        XCTAssertGreaterThan(bottomDark, topDark, "sticker's saucer (near the bottom of its source SVG) should render in the bottom half, not the top (flipped)")
    }

    func testQRLayerRendersUpright() throws {
        // "https://example.com/promo/claim" at correctionLevel M measures to
        // a 31x31-module CIImage (29-module v3 code + 1-module quiet zone on
        // each side) scaled 4x internally = 124px native. Placing the layer
        // at that exact size means no extra outer scaling distorts the
        // module grid math below.
        var design = FlyerDesignFactory.blank()
        design.layers = [.qr(QRLayer(
            id: "qr", x: 0, y: 0, rotation: 0, opacity: 1, locked: nil,
            size: 124, fg: "#17140f", bg: "#ffffff"
        ))]

        let rendered = try FlyerRenderer.image(
            design: design, claimURL: "https://example.com/promo/claim",
            assets: .bundled, pixelMultiplier: 1
        )

        // A real QR's three finder patterns sit at TL/TR/BL, never BR. Their
        // 3x3-module solid-black inner core (modules 2-4 of the 7-module
        // footprint, offset one more module for the quiet zone) is
        // unambiguous — inset=12px, core=12px at 4px/module.
        let inset = 12, core = 12
        func finderCoreDarkness(originX: Int, originY: Int) -> Double? {
            avgDarkness(of: rendered, originX: originX, originY: originY, block: core)
        }
        let tl = finderCoreDarkness(originX: inset, originY: inset)
        let tr = finderCoreDarkness(originX: 124 - inset - core, originY: inset)
        let bl = finderCoreDarkness(originX: inset, originY: 124 - inset - core)
        let br = finderCoreDarkness(originX: 124 - inset - core, originY: 124 - inset - core)

        XCTAssertEqual(tl, 1.0, "top-left finder pattern core should be solid black")
        XCTAssertEqual(tr, 1.0, "top-right finder pattern core should be solid black — this is exactly the corner a Y-flip bug empties out")
        XCTAssertEqual(bl, 1.0, "bottom-left finder pattern core should be solid black")
        XCTAssertNotEqual(br, 1.0, "bottom-right has no finder pattern in a real QR — a Y-flip bug would put one here instead of top-right")
    }

    func testImageLayerIsNotDoubleFlipped() throws {
        // Regression guard: a plain PNG-decoded logo/image is NOT y-up (it's
        // a standard ImageIO decode) and must render as-is. This is the
        // layer kind the flip must NOT touch — pins against reintroducing
        // the blanket fix that broke this case during development.
        let size = 100
        let format = UIGraphicsImageRendererFormat()
        format.scale = 1
        format.opaque = true
        format.preferredRange = .standard
        let srcRenderer = UIGraphicsImageRenderer(size: CGSize(width: size, height: size), format: format)
        let srcImage = srcRenderer.image { ctx in
            UIColor.red.setFill()
            ctx.fill(CGRect(x: 0, y: 0, width: size, height: size / 2))
            UIColor.blue.setFill()
            ctx.fill(CGRect(x: 0, y: size / 2, width: size, height: size / 2))
        }
        guard let pngData = srcImage.pngData(), let decoded = UIImage(data: pngData) else {
            return XCTFail("couldn't build test fixture")
        }

        var design = FlyerDesignFactory.blank()
        let layer = DesignLayer.image(ImageLayer(
            id: "img", x: 0, y: 0, rotation: 0, opacity: 1, locked: nil,
            src: "test://top-bottom", width: Double(size), height: Double(size), slot: nil
        ))
        design.layers = [layer]
        let assets = FlyerRenderAssets.bundled.withImages(["test://top-bottom": decoded])

        let rendered = try FlyerRenderer.image(
            design: design, claimURL: "https://example.com/promo/claim",
            assets: assets, pixelMultiplier: 1
        )

        guard let data = rendered.cgImage?.dataProvider?.data, let pointer = CFDataGetBytePtr(data) else {
            return XCTFail("couldn't read rendered pixels")
        }
        // UIGraphicsImageRenderer contexts are 32BGRA: byte 0 = blue, byte 2 = red.
        XCTAssertGreaterThan(pointer[2], 200, "top-left pixel should be red (the source's top half), not blue (flipped)")
        XCTAssertLessThan(pointer[0], 50, "top-left pixel should not be blue")
    }

    // MARK: - helpers

    private func repositioned(_ layer: DesignLayer, x: Double, y: Double) -> DesignLayer {
        guard case .sticker(var sticker) = layer else { return layer }
        sticker.x = x
        sticker.y = y
        return .sticker(sticker)
    }

    /// Sums "dark" pixels (all channels below `darkThreshold`) in the top
    /// and bottom halves of a `regionSize`x`regionSize` block starting at
    /// the image's origin.
    private func darkMassSplit(of image: UIImage, regionSize: Int, darkThreshold: UInt8) -> (top: Int, bottom: Int) {
        guard let data = image.cgImage?.dataProvider?.data, let ptr = CFDataGetBytePtr(data) else { return (0, 0) }
        let bpp = max(1, (image.cgImage?.bitsPerPixel ?? 32) / 8)
        let bpr = image.cgImage?.bytesPerRow ?? (regionSize * bpp)
        var top = 0, bottom = 0
        for y in 0..<regionSize {
            var rowCount = 0
            for x in 0..<regionSize {
                let off = y * bpr + x * bpp
                if ptr[off] < darkThreshold && ptr[off + 1] < darkThreshold && ptr[off + 2] < darkThreshold { rowCount += 1 }
            }
            if y < regionSize / 2 { top += rowCount } else { bottom += rowCount }
        }
        return (top, bottom)
    }

    private func avgDarkness(of image: UIImage, originX: Int, originY: Int, block: Int) -> Double? {
        guard let data = image.cgImage?.dataProvider?.data, let ptr = CFDataGetBytePtr(data) else { return nil }
        let bpp = max(1, (image.cgImage?.bitsPerPixel ?? 32) / 8)
        let bpr = image.cgImage?.bytesPerRow ?? (originX + block) * bpp
        var darkCount = 0
        for y in originY..<(originY + block) {
            for x in originX..<(originX + block) {
                let off = y * bpr + x * bpp
                if ptr[off] < 128 { darkCount += 1 }
            }
        }
        return Double(darkCount) / Double(block * block)
    }
}
