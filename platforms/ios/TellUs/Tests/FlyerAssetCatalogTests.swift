import XCTest
@testable import TellUs

final class FlyerAssetCatalogTests: XCTestCase {
    func testAllBundledTemplatesDecodeWithMatchingPresetDimensions() throws {
        let catalog = FlyerAssetCatalog(bundle: Bundle.main)
        let templates = try catalog.templates()

        XCTAssertEqual(templates.map(\.id), ["bold-offer", "paper-ticket", "counter-card", "social-drop", "beach-day", "grand-opening", "festive-night", "happy-hour"])
        for template in templates {
            let spec = try XCTUnwrap(FlyerArtboardPresets.spec(for: template.design.artboard.preset))
            XCTAssertEqual(template.design.artboard.w, spec.w, template.id)
            XCTAssertEqual(template.design.artboard.h, spec.h, template.id)
            XCTAssertTrue(template.design.hasUsableQR, template.id)
            for layer in template.design.layers {
                guard case .sticker(let sticker) = layer else { continue }
                XCTAssertNotNil(FlyerAssetCatalog.stickerImageNames[sticker.assetId], template.id)
            }
        }
    }

    func testEveryWireStickerIDMapsToBundledImageName() {
        let expected = [
            "star-burst.svg", "star.svg", "sparkle.svg", "ribbon.svg",
            "tag.svg", "coffee-cup.svg", "heart.svg", "arrow-down.svg",
            "sun.svg", "wave.svg", "palm.svg", "ice-cream.svg", "confetti.svg",
            "balloon.svg", "snowflake.svg", "holly.svg", "cocktail.svg", "moon.svg",
        ]
        XCTAssertEqual(Set(FlyerAssetCatalog.stickerImageNames.keys), Set(expected))
        for imageName in FlyerAssetCatalog.stickerImageNames.values {
            XCTAssertTrue(imageName.hasPrefix("sticker-"))
        }
    }
}
