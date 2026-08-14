import SwiftUI
import XCTest
@testable import TellUs

final class FlyerDesignDecodeTests: XCTestCase {
    private func decode(_ json: String) throws -> FlyerDesign {
        try JSONDecoder().decode(FlyerDesign.self, from: Data(json.utf8))
    }

    private let minimal = """
    {"version":1,"artboard":{"preset":"flyer_letter","w":1275,"h":1650},
     "background":{"kind":"color","color":"paper"},
     "palette":{"ink":"#17140f","paper":"#f3ede0","brand":"#f97316",
                "brandSoft":"#fb923c","accent":"#34d399","muted":"#8a8371"},
     "layers":[
       {"id":"t","type":"text","x":10,"y":20,"rotation":0,"opacity":1,"text":"Hi",
        "fontFamily":"Georgia","fontSize":48,"fontStyle":"bold","fill":"ink",
        "align":"center","width":600,"lineHeight":1.2,"letterSpacing":0},
       {"id":"q","type":"qr","x":100,"y":900,"rotation":0,"opacity":1,
        "size":400,"fg":"#17140f","bg":"#ffffff"}
     ]}
    """

    func testDecodesKnownLayerKinds() throws {
        let design = try decode(minimal)
        XCTAssertEqual(design.layers.count, 2)
        XCTAssertEqual(design.layers[0].kind, "text")
        XCTAssertEqual(design.layers[1].kind, "qr")
        XCTAssertEqual(design.artboard.w, 1275)
    }

    /// The important one. A newer web build can add a layer kind this binary
    /// has never heard of; decoding it to nothing and re-encoding would mean
    /// opening a flyer on the phone and saving it silently deleted a layer.
    func testUnknownLayerKindSurvivesARoundTrip() throws {
        let json = """
        {"version":1,"artboard":{"preset":"flyer_letter","w":1275,"h":1650},
         "background":{"kind":"color","color":"paper"},
         "layers":[
           {"id":"v","type":"video","x":5,"y":6,"src":"https://example.com/a.mp4","loop":true},
           {"id":"q","type":"qr","x":100,"y":900,"rotation":0,"opacity":1,
            "size":400,"fg":"#17140f","bg":"#ffffff"}
         ]}
        """
        let design = try decode(json)
        XCTAssertEqual(design.layers.count, 2)
        XCTAssertEqual(design.layers[0].kind, "unknown")
        XCTAssertEqual(design.layers[0].id, "v")

        let reencoded = try JSONEncoder().encode(design)
        let back = try JSONSerialization.jsonObject(with: reencoded) as? [String: Any]
        let layers = back?["layers"] as? [[String: Any]]
        let unknown = layers?.first
        XCTAssertEqual(unknown?["type"] as? String, "video")
        XCTAssertEqual(unknown?["src"] as? String, "https://example.com/a.mp4")
        XCTAssertEqual(unknown?["loop"] as? Bool, true)
    }

    func testKnownLayerRoundTripsItsFields() throws {
        let design = try decode(minimal)
        let data = try JSONEncoder().encode(design)
        let back = try JSONDecoder().decode(FlyerDesign.self, from: data)
        XCTAssertEqual(design, back)
    }

    func testMissingPaletteDecodesAsNil() throws {
        let json = """
        {"version":1,"artboard":{"preset":"reward_card","w":1050,"h":600},
         "background":{"kind":"color","color":"paper"},
         "layers":[{"id":"q","type":"qr","x":10,"y":10,"rotation":0,"opacity":1,
                    "size":300,"fg":"#17140f","bg":"#ffffff"}]}
        """
        XCTAssertNil(try decode(json).palette)
    }

    func testTextLayerHeightIsDerived() throws {
        let design = try decode(minimal)
        // fontSize 48 x lineHeight 1.2 — mirrors utils/designer.ts:layerBox, so
        // snapping and bounds agree across the two editors.
        XCTAssertEqual(design.layers[0].box.height, 57.6, accuracy: 0.01)
        XCTAssertEqual(design.layers[0].box.width, 600)
    }

    func testWrappedTextBoxIncludesAllLines() throws {
        let design = try decode(minimal.replacingOccurrences(of: "\"Hi\"", with: "\"This is a headline that wraps\""))

        XCTAssertGreaterThan(design.layers[0].box.height, 57.6)
    }

    func testHasUsableQRIgnoresAnOffArtboardCode() throws {
        var design = try decode(minimal)
        XCTAssertTrue(design.hasUsableQR)
        // Parked past the right edge: clipped at render AND export, so counting
        // it would report a flyer as scannable when nothing prints.
        design.layers[1] = design.layers[1].moved(to: CGPoint(x: 4000, y: 900))
        XCTAssertFalse(design.hasUsableQR)
    }
}

final class FlyerColorResolveTests: XCTestCase {
    private let palette = ["ink": "#000000", "paper": "#ffffff"]

    func testHexPassesThrough() {
        XCTAssertEqual(resolveFlyerColor("#ff0000", palette: palette), Color(hex: "#ff0000"))
    }

    func testTokenResolvesFromTheDocumentPalette() {
        XCTAssertEqual(resolveFlyerColor("paper", palette: palette), Color(hex: "#ffffff"))
    }

    /// A palette written by an older build may not define every token. Losing
    /// the custom shade beats painting the layer black.
    func testUnknownTokenFallsBackToTheDefaultPalette() {
        XCTAssertEqual(resolveFlyerColor("brand", palette: palette), Color(hex: "#f97316"))
    }

    func testNilPaletteUsesTheDefault() {
        XCTAssertEqual(resolveFlyerColor("accent", palette: nil), Color(hex: "#34d399"))
    }

    func testShorthandHexExpands() {
        XCTAssertEqual(Color(hex: "#abc"), Color(hex: "#aabbcc"))
    }
}
