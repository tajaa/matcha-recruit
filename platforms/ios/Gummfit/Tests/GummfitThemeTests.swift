import XCTest
@testable import Gummfit

final class GummfitThemeTests: XCTestCase {
    func testOperatorTokensMatchWebPalette() {
        XCTAssertEqual(GummfitTheme.canvasHex, "#09090B")
        XCTAssertEqual(GummfitTheme.surfaceRaisedHex, "#27272A")
        XCTAssertEqual(GummfitTheme.inputBorderHex, "#3F3F46")
        XCTAssertEqual(GummfitTheme.accentHex, "#10B981")
        XCTAssertEqual(GummfitTheme.accentHoverHex, "#34D399")
        XCTAssertEqual(GummfitTheme.dangerHex, "#F87171")
    }

    func testGeometryTokensMatchContract() {
        XCTAssertEqual(GummfitTheme.controlRadius, 8)
        XCTAssertEqual(GummfitTheme.cardRadius, 12)
        XCTAssertEqual(GummfitSpacing.xs, 4)
        XCTAssertEqual(GummfitSpacing.xxxl, 32)
    }
}

final class GummfitStatusPillTests: XCTestCase {
    func testPublishedCatalogCoversAllWebPresets() {
        XCTAssertEqual(CappePublishedThemeCatalog.presets.count, 10)
        XCTAssertEqual(CappePublishedThemeCatalog.presets.map(\.id), [
            "clean", "minimal", "noir", "editorial", "studio",
            "sunset", "terra", "cobalt", "bloom", "press",
        ])
    }

    func testUnknownThemeFallsBackToClean() {
        let config = CappeThemeConfig(raw: ["preset": .string("future")])
        XCTAssertEqual(CappePublishedThemeCatalog.resolved(for: config).id, "clean")
    }
}
