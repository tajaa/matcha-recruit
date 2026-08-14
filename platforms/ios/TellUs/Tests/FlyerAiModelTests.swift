import XCTest
@testable import TellUs

final class FlyerAiModelTests: XCTestCase {
    func testAssistResponseDecodesDesignResultsAndRejections() throws {
        let json = """
        {
          "message":"Moved the QR.",
          "design":{"version":1,"artboard":{"preset":"reward_card","w":1050,"h":600},"background":{"kind":"color","color":"paper"},"layers":[]},
          "ops":[{"name":"move"}],
          "results":[{"ok":true,"summary":"Moved claim QR"}],
          "rejected":[{"op":{"name":"bad"},"reason":"Unsupported operation"}]
        }
        """
        let response = try JSONDecoder().decode(FlyerAssistResponse.self, from: Data(json.utf8))
        XCTAssertEqual(response.message, "Moved the QR.")
        XCTAssertEqual(response.design.artboard.preset, "reward_card")
        XCTAssertEqual(response.results.first?.summary, "Moved claim QR")
        XCTAssertEqual(response.rejected.first?.reason, "Unsupported operation")
        XCTAssertEqual(response.ops.first?.objectValue?["name"]?.stringValue, "move")
    }

    func testAssistRequestUsesWireFieldNames() throws {
        let request = FlyerAssistRequest(
            message: "Make it warmer",
            design: FlyerDesignFactory.blank(),
            history: [FlyerAiHistoryTurn(role: "assistant", content: "Started", ops_summary: nil)],
            selection: FlyerAiSelection(layer: "headline", kind: "text", text: "Hello")
        )
        let object = try JSONSerialization.jsonObject(with: JSONEncoder().encode(request)) as? [String: Any]
        XCTAssertEqual(object?["message"] as? String, "Make it warmer")
        XCTAssertNotNil(object?["design"])
        XCTAssertNotNil(object?["history"])
        XCTAssertEqual((object?["selection"] as? [String: Any])?["layer"] as? String, "headline")
    }
}
