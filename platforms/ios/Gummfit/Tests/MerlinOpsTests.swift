import XCTest
@testable import Gummfit

final class MerlinOpsTests: XCTestCase {
    private func block(_ fields: [String: JSONValue]) -> CappeBlock {
        CappeBlock(fields: fields).withKey("b1")
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
