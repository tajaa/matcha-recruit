import Foundation
import XCTest
@testable import TellUs

final class FlyerDesignEditorTests: XCTestCase {
    func testBlankPresetsMatchWebDimensions() {
        let expected: [(String, Double, Double)] = [
            ("flyer_letter", 1275, 1650),
            ("reward_card", 1050, 600),
            ("social_square", 1080, 1080),
            ("story", 1080, 1920),
        ]

        for (preset, width, height) in expected {
            let design = FlyerDesignFactory.blank(preset: preset)
            XCTAssertEqual(design.artboard.preset, preset)
            XCTAssertEqual(design.artboard.w, width)
            XCTAssertEqual(design.artboard.h, height)
            XCTAssertEqual(design.background.color, "paper")
        }
    }

    func testFactoriesPlaceAddableLayersAndSafeQRColors() {
        let design = FlyerDesignFactory.blank()
        let text = FlyerDesignFactory.text(in: design, text: "Headline")
        let shape = FlyerDesignFactory.shape(in: design, shape: "circle")
        let qr = FlyerDesignFactory.qr(in: design)

        XCTAssertEqual(text.kind, "text")
        XCTAssertEqual(shape.kind, "shape")
        XCTAssertEqual(qr.kind, "qr")
        if case .qr(let layer) = qr {
            XCTAssertEqual(layer.fg, "#17140f")
            XCTAssertEqual(layer.bg, "#ffffff")
            XCTAssertTrue(layer.x >= 0)
            XCTAssertTrue(layer.y >= 0)
        } else {
            XCTFail("Expected QR layer")
        }
    }

    func testTemplateInstantiationRegeneratesIDsAndReplacesLogoSlot() throws {
        let catalog = FlyerAssetCatalog(bundle: Bundle.main)
        let template = try XCTUnwrap(catalog.template(id: "paper-ticket"))
        let instantiated = FlyerDesignFactory.instantiate(template.design, logoURL: "https://example.com/logo.png")

        XCTAssertEqual(instantiated.layers.count, template.design.layers.count)
        XCTAssertNotEqual(
            Set(instantiated.layers.map(\.id)),
            Set(template.design.layers.map(\.id))
        )
        let logo = instantiated.layers.compactMap { layer -> ImageLayer? in
            guard case .image(let image) = layer, image.slot == "logo" else { return nil }
            return image
        }
        XCTAssertEqual(logo.count, 1)
        XCTAssertEqual(logo.first?.src, "https://example.com/logo.png")
    }

    func testTemplateWithoutLogoDropsOnlyLogoSlot() throws {
        let catalog = FlyerAssetCatalog(bundle: Bundle.main)
        let template = try XCTUnwrap(catalog.template(id: "paper-ticket"))
        let instantiated = FlyerDesignFactory.instantiate(template.design, logoURL: nil)

        XCTAssertEqual(instantiated.layers.count, template.design.layers.count - 1)
        XCTAssertFalse(instantiated.layers.contains {
            if case .image(let image) = $0 { return image.slot == "logo" }
            return false
        })
        XCTAssertTrue(instantiated.hasUsableQR)
    }

    func testTemplateInstantiationCarriesTemplatePalette() throws {
        let catalog = FlyerAssetCatalog(bundle: Bundle.main)
        let template = try XCTUnwrap(catalog.template(id: "beach-day"))
        let instantiated = FlyerDesignFactory.instantiate(template.design, logoURL: nil)

        XCTAssertEqual(instantiated.palette, template.design.palette)
        XCTAssertEqual(instantiated.palette?["brand"], "#0e9bbd")
    }

    func testRetargetClampsKnownLayersAndPreservesUnknownLayer() throws {
        var design = FlyerDesignFactory.blank()
        let text = FlyerDesignFactory.text(in: design, text: "Hi")
        design.layers = [text, .unknown(id: "video", raw: .object([
            "id": .string("video"), "type": .string("video"), "src": .string("https://example.com/video.mp4")
        ]))]

        let retargeted = design.retargeted(to: "reward_card")
        XCTAssertEqual(retargeted.artboard.preset, "reward_card")
        XCTAssertEqual(retargeted.layers[1].id, "video")
        XCTAssertEqual(retargeted.layers[1].kind, "unknown")
        XCTAssertEqual(retargeted.layers[0].origin.x, 157, accuracy: 1)
        XCTAssertGreaterThanOrEqual(retargeted.layers[0].origin.y, 0)
    }

    func testLayerMutationsDoNotChangeUnrelatedLayers() {
        let design = FlyerDesignFactory.blank()
        let first = FlyerDesignFactory.text(in: design, text: "First")
        let second = FlyerDesignFactory.text(in: design, text: "Second")
        var withLayers = design
        withLayers.layers = [first, second]

        let duplicate = withLayers.duplicatingLayer(id: first.id)
        XCTAssertEqual(duplicate.layers.count, 3)
        XCTAssertEqual(duplicate.layers[1].id, second.id)
        XCTAssertNotEqual(duplicate.layers[2].id, first.id)

        let removed = duplicate.removingLayer(id: second.id)
        XCTAssertFalse(removed.layers.contains { $0.id == second.id })

        let moved = removed.reorderingLayer(id: first.id, direction: .forward)
        XCTAssertEqual(moved.layers.last?.id, first.id)
    }
}
