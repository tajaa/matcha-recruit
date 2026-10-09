import XCTest
@testable import Matcha

/// The chat model picker renders the server's rows (`workspace.chat_models`)
/// rather than re-deriving which models a plan gets. The label, the checkmark
/// and the value sent must all name the model the turn actually runs.
final class ModelPickerTests: XCTestCase {

    private func picker(_ json: String) throws -> MWModelPicker {
        let workspace = try JSONDecoder().decode(MWWorkspaceFlags.self, from: Data(json.utf8))
        return MWModelPicker(workspace: workspace)
    }

    private let freePlan = """
    {"chat_models": [
        {"id": "gemini-3.5-flash-lite", "locked": false}, {"id": "gemini-3.7-flash", "locked": false},
        {"id": "claude-haiku-5-5", "locked": false}, {"id": "claude-sonnet-5-5", "locked": true}],
     "default_chat_model": "gemini-3.7-flash"}
    """

    private let adminHaiku = """
    {"chat_models": [{"id": "claude-haiku-5-5", "locked": false}, {"id": "claude-sonnet-5-5", "locked": true}],
     "default_chat_model": "claude-haiku-5-5"}
    """

    func testUntilEntitlementsLoadOnlyGeminiRows() {
        let picker = MWModelPicker(workspace: nil)
        XCTAssertEqual(picker.options.map(\.id), ["flash-lite", "flash"])
        XCTAssertEqual(picker.option(for: "claude-haiku")?.id, "flash")
    }

    func testLockedRowIsShownButNeverSentOrChecked() throws {
        let picker = try picker(freePlan)
        let sonnet = try XCTUnwrap(picker.options.first { $0.id == "claude-sonnet" })
        XCTAssertTrue(picker.isLocked(sonnet))
        XCTAssertNil(picker.value(for: "claude-sonnet"))
        // Label and checkmark fall to the server default, the model that runs.
        XCTAssertEqual(picker.option(for: "claude-sonnet")?.id, "flash")
    }

    func testAdminModelHidesGeminiAndOwnsTheCheckmark() throws {
        let picker = try picker(adminHaiku)
        XCTAssertEqual(picker.options.map(\.id), ["claude-haiku", "claude-sonnet"])
        // A stored Gemini pick reads as the admin model: one row is checked.
        XCTAssertEqual(picker.option(for: "flash")?.id, "claude-haiku")
        XCTAssertNil(picker.value(for: "flash"))
        XCTAssertEqual(picker.value(for: "claude-haiku"), "claude-haiku-5-5")
    }

    func testUnlockedPickIsKept() throws {
        let picker = try picker(freePlan)
        XCTAssertEqual(picker.option(for: "claude-haiku")?.id, "claude-haiku")
        XCTAssertEqual(picker.value(for: "flash-lite"), "gemini-3.5-flash-lite")
    }
}
