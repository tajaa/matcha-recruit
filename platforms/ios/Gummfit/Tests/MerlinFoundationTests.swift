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

    func testCanvasIntegerRoundTripsAsAnIntegralJSONNumber() throws {
        let block = CappeBlock(fields: [
            "type": .string("canvas"),
            "elements": .array([.object(["id": .string("e1"), "kind": .string("text"), "d": .object(["x": .number(3)])])]),
        ])
        let encoded = try JSONEncoder().encode(block)
        let object = try XCTUnwrap(JSONSerialization.jsonObject(with: encoded) as? [String: Any])
        let elements = try XCTUnwrap(object["elements"] as? [[String: Any]])
        let d = try XCTUnwrap(elements[0]["d"] as? [String: Any])
        XCTAssertEqual(d["x"] as? Double, 3)
        XCTAssertFalse(String(data: encoded, encoding: .utf8)?.contains("3.0") ?? true)
    }

    func testPageStatusAndEmptyContentDecode() throws {
        let json = #"{"id":"p1","site_id":"s1","title":"Home","slug":"home","content":{},"sort_order":0,"status":"archived","created_at":"now","updated_at":"now"}"#
        let page = try JSONDecoder().decode(CappePage.self, from: Data(json.utf8))
        XCTAssertEqual(page.status, .archived)
        XCTAssertTrue(page.blocks.isEmpty)

        let unknown = json.replacingOccurrences(of: "archived", with: "future")
        XCTAssertEqual(try JSONDecoder().decode(CappePage.self, from: Data(unknown.utf8)).status, .unknown)
    }

    func testKeylessDecodedBlocksReceiveStableDistinctKeys() throws {
        let json = #"{"id":"p1","site_id":"s1","title":"Home","slug":"home","content":{"blocks":[{"type":"hero"},{"type":"faq"}]},"sort_order":0,"status":"draft","created_at":"now","updated_at":"now"}"#
        let page = try JSONDecoder().decode(CappePage.self, from: Data(json.utf8))
        let keys = page.blocks.map(\._k)
        XCTAssertEqual(keys.count, 2)
        XCTAssertTrue(keys.allSatisfy { !$0.isEmpty })
        XCTAssertEqual(Set(keys).count, 2)
        XCTAssertEqual(page.blocks.map(\.id), keys)
    }

    func testJSONValueNumericConversionsAreSafeAndNSNumberAware() {
        XCTAssertEqual(JSONValue.number(1e30).intValue, Int.max)
        XCTAssertEqual(JSONValue.number(-1e30).intValue, Int.min)
        XCTAssertEqual(JSONValue.from(NSNumber(value: 1)).doubleValue, 1)
        XCTAssertNil(JSONValue.from(NSNumber(value: 1)).boolValue)
        XCTAssertEqual(JSONValue.from(NSNumber(value: true)).boolValue, true)
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

    func testStoredMessageUnappliedRequiresOpsWithoutResults() throws {
        let base = #"{"id":"m1","role":"assistant","content":"Done","attachments":null,"tier":"lite","created_at":"now"}"#
        let unapplied = base.replacingOccurrences(of: "\"attachments\":null", with: "\"attachments\":null,\"ops\":[]")
        let applied = unapplied.replacingOccurrences(of: "\"ops\":[]", with: "\"ops\":[],\"results\":[]")
        XCTAssertTrue(try JSONDecoder().decode(CappeMerlinStoredMessage.self, from: Data(unapplied.utf8)).isUnapplied)
        XCTAssertFalse(try JSONDecoder().decode(CappeMerlinStoredMessage.self, from: Data(applied.utf8)).isUnapplied)
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
