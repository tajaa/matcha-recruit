import XCTest
@testable import Gummfit

final class MerlinOpsTests: XCTestCase {
    private func block(_ fields: [String: JSONValue]) -> CappeBlock {
        CappeBlock(fields: fields).withKey("b1")
    }

    private var schema: CappeEditorSchema {
        CappeEditorSchema(
            blocks: ["faq": .init(label: "FAQ", fields: [:], make: ["type": .string("faq"), "heading": .string("FAQ")])],
            blockOrder: ["faq"],
            design: ["motion": ["heading": .object([:])]],
            theme: .init(keys: [], prefixes: [], modes: ["light", "dark"]),
            themePresets: [],
            fontPairings: [],
            sectionPresets: [],
            styleRecipes: [],
            limits: .init(maxOpsPerTurn: 20, canvas: .init(elementKinds: ["text"], maxElements: 200, gridCols: 24, mobileGridCols: 8))
        )
    }

    func testNestedListFieldApplies() {
        let source = block([
            "type": .string("features"),
            "items": .array([.object(["title": .string("old")])]),
        ])
        let updated = applyFieldPath(block: source, path: "items.0.title", value: .string("new"))
        XCTAssertEqual(updated?.fields["items"]?.arrayValue?[0].objectValue?["title"]?.stringValue, "new")
    }

    func testListIndexEqualToCountAppends() {
        let source = block(["type": .string("features"), "items": .array([])])
        let updated = applyFieldPath(block: source, path: "items.0.title", value: .string("new"))
        XCTAssertEqual(updated?.fields["items"]?.arrayValue?.count, 1)
        XCTAssertEqual(updated?.fields["items"]?.arrayValue?[0].objectValue?["title"]?.stringValue, "new")
    }

    func testReservedPathIsRefused() {
        let source = block(["type": .string("hero"), "heading": .string("old")])
        XCTAssertNil(applyFieldPath(block: source, path: "_k", value: .string("bad")))
        XCTAssertNil(applyFieldPath(block: source, path: "type.value", value: .string("bad")))
    }

    func testIndexPastEndIsRefused() {
        let source = block(["type": .string("features"), "items": .array([])])
        XCTAssertNil(applyFieldPath(block: source, path: "items.2.title", value: .string("bad")))
    }

    func testNamedKeyIntoListIsRefused() {
        let source = block(["type": .string("features"), "items": .array([.object(["title": .string("old")])])])
        let result = applyMerlinOps(blocks: [source], theme: [:], ops: [.setField(block: "b1", path: "items.title", value: .string("bad"))], schema: nil)
        XCTAssertFalse(result.results[0].ok)
        XCTAssertEqual(result.blocks, [source])
        XCTAssertTrue(result.results[0].summary.contains("doesn't match"))
    }

    func testMerlinTurnAppliesFieldAndTheme() {
        let source = block(["type": .string("hero"), "heading": .string("old")])
        let result = applyMerlinOps(
            blocks: [source],
            theme: [:],
            ops: [
                .setField(block: "b1", path: "heading", value: .string("new")),
                .setTheme(key: "colors.brand", value: .string("#ffee00")),
            ],
            schema: nil
        )
        XCTAssertTrue(result.changed)
        XCTAssertEqual(result.blocks[0].fields["heading"]?.stringValue, "new")
        XCTAssertEqual(result.theme["colors"]?.objectValue?["accent"]?.stringValue, "#ffee00")
        XCTAssertEqual(result.theme["colors"]?.objectValue?["brandText"]?.stringValue, "#10120a")
    }

    func testDesignClearAndUnknownKeyAreHandled() {
        let source = block(["type": .string("hero"), "_design": .object(["motion": .object(["heading": .string("shimmer")])])])
        let result = applyMerlinOps(
            blocks: [source], theme: [:],
            ops: [
                .setDesign(block: "b1", group: "motion", key: "heading", value: .string("")),
                .setDesign(block: "b1", group: "motion", key: "bogus", value: .string("x")),
            ], schema: schema
        )
        XCTAssertTrue(result.results[0].ok)
        XCTAssertFalse(result.results[1].ok)
        XCTAssertNil(result.blocks[0].design["motion"]?.objectValue?["heading"])
    }

    func testDesignBulkNoMatchDoesNotChangeBlocks() {
        let source = block(["type": .string("hero")])
        let result = applyMerlinOps(
            blocks: [source], theme: [:],
            ops: [.setDesignBulk(blocks: ["missing"], design: ["motion": ["heading": .string("rise")]])], schema: nil
        )
        XCTAssertFalse(result.changed)
        XCTAssertEqual(result.blocks, [source])
        XCTAssertFalse(result.results[0].ok)
    }

    func testAddBlockUsesSchemaMakeAndTempId() {
        let result = applyMerlinOps(
            blocks: [block(["type": .string("hero")])], theme: [:],
            ops: [.addBlock(type: "faq", at: 99, content: ["heading": .string("Questions")], design: nil, preset: nil, id: "new-1")],
            schema: schema
        )
        XCTAssertEqual(result.blocks.count, 2)
        XCTAssertEqual(result.blocks[1].fields["heading"]?.stringValue, "Questions")
        XCTAssertEqual(result.tempIdMap["new-1"], result.blocks[1]._k)
    }

    func testAddBlockFallsBackToValidatedTypeWithoutSchema() {
        let result = applyMerlinOps(
            blocks: [], theme: [:],
            ops: [.addBlock(type: "faq", at: 0, content: ["heading": .string("Questions")], design: nil, preset: nil, id: nil)],
            schema: nil
        )
        XCTAssertTrue(result.results[0].ok)
        XCTAssertEqual(result.blocks[0].type, "faq")
        XCTAssertEqual(result.blocks[0].fields["heading"]?.stringValue, "Questions")
    }

    func testPresetUsesOfflineThemeFallbackWithoutSchema() {
        let result = applyMerlinOps(
            blocks: [], theme: ["colors": .object(["brand": .string("#old")])],
            ops: [.setTheme(key: "preset", value: .string("noir"))], schema: nil
        )
        XCTAssertTrue(result.results[0].ok)
        XCTAssertEqual(result.theme["preset"]?.stringValue, "noir")
        XCTAssertEqual(result.theme["mode"]?.stringValue, "dark")
        XCTAssertEqual(result.theme["colors"]?.objectValue?["brand"]?.stringValue, "#A3E635")
    }

    func testMoveToSameIndexIsNoOp() {
        let source = block(["type": .string("hero")])
        let result = applyMerlinOps(blocks: [source], theme: [:], ops: [.moveBlock(block: "b1", to: 0)], schema: nil)
        XCTAssertFalse(result.changed)
        XCTAssertTrue(result.results[0].ok)
    }

    func testThemeModeClearsSurfaceColorsOnly() {
        let result = applyMerlinOps(
            blocks: [],
            theme: ["mode": .string("light"), "colors": .object([
                "bg": .string("#fff"), "surface": .string("#eee"), "text": .string("#111"),
                "muted": .string("#777"), "border": .string("#ddd"), "brand": .string("#0f0"),
                "accent": .string("#0f0"), "brandText": .string("#fff"),
            ])],
            ops: [.setTheme(key: "mode", value: .string("dark"))], schema: nil
        )
        let colors = result.theme["colors"]?.objectValue ?? [:]
        XCTAssertEqual(result.theme["mode"]?.stringValue, "dark")
        for key in ["bg", "surface", "text", "muted", "border"] { XCTAssertNil(colors[key]) }
        XCTAssertEqual(colors["brand"]?.stringValue, "#0f0")
        XCTAssertEqual(colors["accent"]?.stringValue, "#0f0")
        XCTAssertEqual(colors["brandText"]?.stringValue, "#fff")
    }

    func testThemePathPreservesAllSegments() {
        let result = applyMerlinOps(
            blocks: [], theme: ["style": .object([:])],
            ops: [.setTheme(key: "style.card.radius", value: .string("lg"))], schema: nil
        )
        let style = result.theme["style"]?.objectValue ?? [:]
        XCTAssertEqual(style["card.radius"]?.stringValue, "lg")
        XCTAssertNil(style["card"])
    }

    func testNumericSegmentIntoObjectIsRefused() {
        let source = block(["type": .string("hero"), "settings": .object(["existing": .string("value")])])
        XCTAssertNil(applyFieldPath(block: source, path: "settings.0.title", value: .string("bad")))
    }

    func testGenerateImageIsNotReportedAsAppliedBySynchronousFold() {
        let result = applyMerlinOps(
            blocks: [block(["type": .string("hero")])], theme: [:],
            ops: [.generateImage(block: "b1", field: "image", background: false, prompt: "photo", aspect: nil, imageSize: nil)], schema: nil
        )
        XCTAssertFalse(result.results[0].ok)
        XCTAssertFalse(result.changed)
    }

    func testCanvasAddRespectsLimitAndCanvasUpdateCannotChangeIdentity() {
        var elements: [JSONValue] = (0..<200).map { .object(["id": .string("e\($0)"), "kind": .string("text")]) }
        let full = block(["type": .string("canvas"), "elements": .array(elements)])
        let refused = applyMerlinOps(blocks: [full], theme: [:], ops: [.canvasAdd(block: "b1", element: ["kind": .string("text")])], schema: nil)
        XCTAssertFalse(refused.results[0].ok)

        elements = [.object(["id": .string("e1"), "kind": .string("text"), "text": .string("before")])]
        let canvas = block(["type": .string("canvas"), "elements": .array(elements)])
        let updated = applyMerlinOps(blocks: [canvas], theme: [:], ops: [.canvasUpdate(block: "b1", el: "e1", patch: ["id": .string("bad"), "kind": .string("image"), "text": .string("after")])], schema: nil)
        let element = updated.blocks[0].fields["elements"]?.arrayValue?[0].objectValue ?? [:]
        XCTAssertEqual(element["id"]?.stringValue, "e1")
        XCTAssertEqual(element["kind"]?.stringValue, "text")
        XCTAssertEqual(element["text"]?.stringValue, "after")
    }

    func testJSONDecoderRecognizesEveryValidatedOperation() {
        let values: [JSONValue] = [
            .object(["op": .string("set_field"), "block": .string("b1"), "path": .string("heading")]),
            .object(["op": .string("set_design"), "block": .string("b1"), "group": .string("motion"), "key": .string("heading")]),
            .object(["op": .string("set_design_bulk"), "blocks": .array([.string("b1")]), "design": .object([:])]),
            .object(["op": .string("add_block"), "type": .string("faq"), "at": .number(0)]),
            .object(["op": .string("duplicate_block"), "block": .string("b1")]),
            .object(["op": .string("remove_block"), "block": .string("b1")]),
            .object(["op": .string("move_block"), "block": .string("b1"), "to": .number(0)]),
            .object(["op": .string("set_theme"), "key": .string("mode"), "value": .string("dark")]),
            .object(["op": .string("canvas_add"), "block": .string("b1"), "element": .object(["kind": .string("text")])]),
            .object(["op": .string("canvas_update"), "block": .string("b1"), "el": .string("e1"), "patch": .object([:])]),
            .object(["op": .string("canvas_remove"), "block": .string("b1"), "el": .string("e1")]),
            .object(["op": .string("generate_image"), "block": .string("b1"), "prompt": .string("photo")]),
        ]
        for value in values {
            if case .unrecognized = MerlinOp(json: value) { XCTFail("Operation was not decoded: \(value)") }
        }
    }

    func testDuplicateCreatesFreshKeysAndCanvasElementIds() {
        let source = block([
            "type": .string("canvas"),
            "_design": .object(["anchor": .object(["id": .string("anchor-1")])]),
            "elements": .array([.object(["id": .string("element-1"), "kind": .string("text")])]),
        ])
        let result = applyMerlinOps(
            blocks: [source], theme: [:],
            ops: [.duplicateBlock(block: "b1", at: nil, id: "copy")], schema: nil
        )
        XCTAssertEqual(result.blocks.count, 2)
        XCTAssertNotEqual(result.blocks[0]._k, result.blocks[1]._k)
        XCTAssertNil(result.blocks[1].design["anchor"]?.objectValue?["id"])
        XCTAssertNotEqual(result.blocks[0].fields["elements"]?.arrayValue?[0].objectValue?["id"], result.blocks[1].fields["elements"]?.arrayValue?[0].objectValue?["id"])
        XCTAssertEqual(result.tempIdMap["copy"], result.blocks[1]._k)
    }
}
