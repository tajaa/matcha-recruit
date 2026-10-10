import XCTest
@testable import MatchaSchedule

final class HuumeTests: XCTestCase {
    func testStreamFramesBecomeEvents() {
        XCTAssertEqual(HuumeSSE.parse(line: #"data: {"type":"status","message":"Reading the week"}"#), .status("Reading the week"))
        XCTAssertEqual(HuumeSSE.parse(line: #"data: {"type":"step","data":{"seq":1,"tool":"get_schedule_overview","kind":"read","label":"Looked at the week","status":"ok"}}"#),
                       .step("Looked at the week"))
        XCTAssertEqual(HuumeSSE.parse(line: #"data: {"type":"error","message":"Model hiccup"}"#), .error("Model hiccup"))
        XCTAssertEqual(HuumeSSE.parse(line: "data: [DONE]"), .done)
        // Skipped: keepalives, usage, blank lines, comments, junk.
        XCTAssertNil(HuumeSSE.parse(line: #"data: {"type":"keepalive"}"#))
        XCTAssertNil(HuumeSSE.parse(line: #"data: {"type":"usage","data":{"stage":"estimate"}}"#))
        XCTAssertNil(HuumeSSE.parse(line: ""))
        XCTAssertNil(HuumeSSE.parse(line: ": ping"))
        XCTAssertNil(HuumeSSE.parse(line: "data: {not json"))
    }

    func testCompleteCarriesTheMessagesAndTheStagedAction() throws {
        let line = #"""
        data: {"type":"complete","data":{"user_message":{"id":"u1","thread_id":"t","role":"user","content":"Fill the open shifts","version_created":null,"metadata":null,"created_at":"2026-10-10T10:00:00Z"},"assistant_message":{"id":"a1","thread_id":"t","role":"assistant","content":"I staged **2** assignments.","version_created":null,"metadata":{"huume_steps":[]},"created_at":"2026-10-10T10:00:05Z"},"current_state":{"huume_action":{"type":"schedule_change","status":"proposed","confirm_id":"c1","pill_text":"Put Sam on Mon 6:30 AM and Kai on Tue 6:30 AM?\nReply confirm.","review":{"assignments":[]}},"other":{"x":1}},"version":3,"task_type":null,"pdf_url":null,"token_usage":null}}
        """#
        guard case .complete(let user, let assistant, let state)? = HuumeSSE.parse(line: line) else {
            return XCTFail("expected a complete event")
        }
        XCTAssertEqual(user?.content, "Fill the open shifts")
        XCTAssertEqual(assistant?.isUser, false)
        let action = try XCTUnwrap(state?.action)
        XCTAssertTrue(action.awaitingConfirmation)
        XCTAssertEqual(action.question, "Put Sam on Mon 6:30 AM and Kai on Tue 6:30 AM?")
        XCTAssertFalse(action.changedSchedule)
    }

    func testAStateShapeThisBuildDoesNotKnowOnlyHidesTheCard() throws {
        let state = try JSONDecoder().decode(HuumeState.self, from: Data(#"""
        {"huume_action":{"type":"schedule_week_draft","status":"applied"},
         "huume_choice":{"question":"Which store?","options":[{"label":"Downtown","send":"Downtown"},{"label":"Mission"}],"kind":"single"}}
        """#.utf8))
        XCTAssertTrue(try XCTUnwrap(state.action).changedSchedule)
        XCTAssertEqual(state.choice?.options.map(\.label), ["Downtown", "Mission"])

        let odd = try JSONDecoder().decode(HuumeState.self, from: Data(#"{"huume_action":"weird","huume_choice":[]}"#.utf8))
        XCTAssertNil(odd.action)
        XCTAssertNil(odd.choice)
    }

    func testTheCardFallsBackToPlainWords() throws {
        let draft = try JSONDecoder().decode(HuumeAction.self, from: Data(#"{"type":"schedule_week_draft","status":"proposed"}"#.utf8))
        XCTAssertEqual(draft.question, "Add this week to the schedule as drafts?")
        let other = try JSONDecoder().decode(HuumeAction.self, from: Data(#"{"type":"schedule_note","status":"proposed","summary":"Save a note for Sam?"}"#.utf8))
        XCTAssertEqual(other.question, "Save a note for Sam?")
    }

    func testSessionDecodes() throws {
        let session = try JSONDecoder().decode(HuumeSession.self, from: Data(#"""
        {"session_id":"s","thread_id":"t","location_id":"l","week_start":"2026-10-12","week_end":"2026-10-18",
         "title":"Schedule","messages":[],"current_state":{},"version":1,"available_models":[],"default_model":"gpt-5.6-luna"}
        """#.utf8))
        XCTAssertEqual(session.thread_id, "t")
        XCTAssertNil(session.current_state.action)
    }
}
