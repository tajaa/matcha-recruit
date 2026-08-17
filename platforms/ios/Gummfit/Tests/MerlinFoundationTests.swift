import XCTest
@testable import Gummfit

final class MerlinFoundationTests: XCTestCase {
    func testPageStripsClientKeyButPreservesUnknownFields() throws {
        let block = CappeBlock(fields: [
            "type": .string("hero"), "_k": .string("client-key"),
            "futureField": .object(["value": .number(3)]),
        ])
        let encoded = try JSONEncoder().encode(block.strippingKey())
        let object = try XCTUnwrap(JSONSerialization.jsonObject(with: encoded) as? [String: Any])
        XCTAssertNil(object["_k"])
        XCTAssertEqual((object["futureField"] as? [String: Any])?["value"] as? Double, 3)
    }

    func testPageUpdateOmitsNilFields() throws {
        let update = CappePageUpdate(title: "New title", slug: nil, content: nil, sort_order: nil, status: nil)
        let object = try XCTUnwrap(JSONSerialization.jsonObject(with: JSONEncoder().encode(update)) as? [String: Any])
        XCTAssertEqual(object["title"] as? String, "New title")
        XCTAssertEqual(object.count, 1)
    }

    func testUnknownMerlinFrameDoesNotThrow() throws {
        let frame = try JSONDecoder().decode(CappeMerlinFrame.self, from: Data(#"{"type":"future","data":{}}"#.utf8))
        if case .unknown = frame { } else { XCTFail("Expected unknown frame") }
    }

    func testResultFrameDecodes() throws {
        let data = Data(#"{"type":"result","data":{"message":"Done","ops":[],"rejected":[],"tier":"lite","routed":false,"conversation_id":null,"message_id":"m1","steps":[]}}"#.utf8)
        let frame = try JSONDecoder().decode(CappeMerlinFrame.self, from: data)
        guard case .result(let result) = frame else { return XCTFail("Expected result frame") }
        XCTAssertEqual(result.message, "Done")
        XCTAssertEqual(result.message_id, "m1")
    }

    func testSchemaDecodesListAndThemeMetadata() throws {
        let data = Data("""
        {
          "blocks":{"features":{"label":"Features","fields":{"items":{"kind":"list","label":"Items","item":{"title":{"kind":"text","label":"Title"}},"newItem":{"title":""},"addLabel":"Add feature"}},"make":{"type":"features"}}},
          "blockOrder":["features"],"design":{},"theme":{"keys":[],"prefixes":[],"modes":["light","dark"]},
          "themePresets":[{"id":"clean","name":"Clean","blurb":"Bright","premium":false,"mode":"light","config":{"mode":"light"},"swatch":{"bg":"#fff","surface":"#eee","brand":"#000","text":"#111"}}],
          "fontPairings":[{"id":"inter","label":"Inter / Inter","heading":"Inter","body":"Inter"}],
          "sectionPresets":[],"styleRecipes":[],"limits":{"maxOpsPerTurn":20,"canvas":{"elementKinds":["text"],"maxElements":200,"gridCols":24,"mobileGridCols":8}}
        }
        """.utf8)
        let schema = try JSONDecoder().decode(CappeEditorSchema.self, from: data)
        XCTAssertEqual(schema.blocks["features"]?.fields["items"]?.item?["title"]?.kind, "text")
        XCTAssertEqual(schema.preset("clean")?.config["mode"]?.stringValue, "light")
    }
}

@MainActor
final class EditorHistoryTests: XCTestCase {
    private let initial = EditorSnapshot(blocks: [], title: "A", status: .draft, theme: [:], meta: [:])

    func testUndoRedoRestoresSnapshots() {
        let history = EditorHistory(initial: initial)
        history.record(EditorSnapshot(blocks: [], title: "B", status: .draft, theme: [:], meta: [:]), coalescing: false)
        XCTAssertEqual(history.undo()?.title, "A")
        XCTAssertEqual(history.redo()?.title, "B")
    }

    func testCheckpointSeparatesCoalescedEdits() {
        let history = EditorHistory(initial: initial, coalesceWindow: 60)
        history.record(EditorSnapshot(blocks: [], title: "B", status: .draft, theme: [:], meta: [:]), coalescing: true)
        history.checkpoint()
        history.record(EditorSnapshot(blocks: [], title: "C", status: .draft, theme: [:], meta: [:]), coalescing: true)
        XCTAssertEqual(history.undo()?.title, "B")
    }
}
