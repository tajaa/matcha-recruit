import XCTest
@testable import TellUs

final class IntakeSubmissionEncodingTests: XCTestCase {
    func testHoneypotAlwaysEmpty() throws {
        let submission = IntakeSubmission(
            category: "service", sentiment: "positive", title: nil, description: "great",
            reporter_contact: nil, rating: 5, post_as_review: true, media_keys: [],
            website: "", answers: []
        )
        let data = try JSONEncoder().encode(submission)
        let json = String(data: data, encoding: .utf8)!
        XCTAssertTrue(json.contains("\"website\":\"\""))
    }

    func testAnswersTrimmedNonEmpty() {
        // Calls the actual production transform (IntakeViewModel.trimmedAnswers)
        // instead of re-implementing it, so a regression there fails this test.
        let raw: [String: String] = ["p1": " hi ", "p2": "  "]
        let answers = IntakeViewModel.trimmedAnswers(raw)
        XCTAssertEqual(answers.count, 1)
        XCTAssertEqual(answers.first?.prompt_id, "p1")
        XCTAssertEqual(answers.first?.answer, "hi")
    }

    func testNilOptionalsAreOmitted() throws {
        // Synthesized Encodable calls encodeIfPresent for Optional stored
        // properties, which OMITS the key entirely for nil rather than
        // writing "null" — assert the actual (correct) encoder behavior so
        // this doesn't silently bit-rot if IntakeSubmission grows a custom
        // encode(to:) later.
        let submission = IntakeSubmission(
            category: "service", sentiment: "neutral", title: nil, description: "ok",
            reporter_contact: nil, rating: nil, post_as_review: false, media_keys: [],
            website: "", answers: []
        )
        let data = try JSONEncoder().encode(submission)
        let json = String(data: data, encoding: .utf8)!
        XCTAssertFalse(json.contains("\"title\""))
        XCTAssertFalse(json.contains("\"rating\""))
        XCTAssertTrue(json.contains("\"description\":\"ok\""))
    }
}
