import XCTest
@testable import Matcha

/// The assistant's model menu renders the server's rows
/// (`workspace.assistant_models`). The label names the model that runs, and
/// only a pick the server offers is ever sent.
final class AssistantModelMenuTests: XCTestCase {

    private func menu(_ json: String) throws -> AssistantModelMenu {
        let workspace = try JSONDecoder().decode(MWWorkspaceFlags.self, from: Data(json.utf8))
        return AssistantModelMenu(workspace: workspace)
    }

    private let three = """
    {"espresso_assistant": true,
     "assistant_models": [
        {"id": "gpt-5.6-luna", "label": "OpenAI Luna"},
        {"id": "claude-haiku-5-5", "label": "Claude Haiku 5.5"},
        {"id": "claude-sonnet-5-5", "label": "Claude Sonnet 5.5"}],
     "default_assistant_model": "claude-haiku-5-5"}
    """

    func testAnOlderServerOrOneModelMeansNoMenu() throws {
        XCTAssertFalse(try menu(#"{"espresso_assistant": true}"#).hasChoice)
        XCTAssertFalse(AssistantModelMenu(workspace: nil).hasChoice)
        let lunaOnly = try menu(#"{"assistant_models": [{"id": "gpt-5.6-luna", "label": "OpenAI Luna"}], "default_assistant_model": "gpt-5.6-luna"}"#)
        XCTAssertFalse(lunaOnly.hasChoice)
        XCTAssertNil(AssistantModelMenu(workspace: nil).value(for: "claude-sonnet-5-5"))
    }

    func testNoPickShowsTheServerDefaultAndSendsNothing() throws {
        let menu = try menu(three)
        XCTAssertTrue(menu.hasChoice)
        XCTAssertEqual(menu.current("")?.label, "Claude Haiku 5.5")
        XCTAssertNil(menu.value(for: ""))
    }

    func testAnOfferedPickIsShownAndSent() throws {
        let menu = try menu(three)
        XCTAssertEqual(menu.current("claude-sonnet-5-5")?.label, "Claude Sonnet 5.5")
        XCTAssertEqual(menu.value(for: "claude-sonnet-5-5"), "claude-sonnet-5-5")
        XCTAssertEqual(menu.value(for: "gpt-5.6-luna"), "gpt-5.6-luna")
    }

    func testAPickTheServerStoppedOfferingFallsBackToTheDefault() throws {
        let menu = try menu(three)
        XCTAssertEqual(menu.current("claude-opus-9")?.label, "Claude Haiku 5.5")
        XCTAssertNil(menu.value(for: "claude-opus-9"))
    }
}
