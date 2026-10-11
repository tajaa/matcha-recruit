import XCTest
@testable import Matcha

/// Which document a thread's state is, and what the asset canvas reads off
/// it (title, copy text, file names, "edited" time). Pure functions over
/// sample state; nothing here touches the network or the signed-in session.
final class AssetInferenceTests: XCTestCase {

    private func state(_ pairs: [String: Any]) -> [String: AnyCodable] {
        pairs.mapValues { AnyCodable($0) }
    }

    // MARK: - inferMWTaskType

    func testPolicyKeysInferPolicy() {
        XCTAssertEqual(inferMWTaskType(from: state(["policy_title": "Remote work"])), .policy)
        XCTAssertEqual(inferMWTaskType(from: state(["policy_status": "generating"])), .policy)
        XCTAssertEqual(inferMWTaskType(from: state(["policy_content": "# Policy"])), .policy)
    }

    func testPolicyOutranksWorkbookKeysLikeTheServer() {
        // `_infer_skill_from_state` checks policy_* before sections.
        let s = state(["policy_title": "PTO", "sections": [AnyCodable(["title": AnyCodable("x")])]])
        XCTAssertEqual(inferMWTaskType(from: s), .policy)
    }

    func testOnboardingWithBatchStatusIsOnboarding() {
        let s = state(["employees": [AnyCodable(["first_name": AnyCodable("Ada")])], "batch_status": "collecting"])
        XCTAssertEqual(inferMWTaskType(from: s), .onboarding)
    }

    func testResumeBatchMappingsAreUnchanged() {
        XCTAssertEqual(inferMWTaskType(from: state(["candidates": [AnyCodable]()])), .resumeBatch)
        XCTAssertEqual(inferMWTaskType(from: state(["batch_title": "Q4 hiring"])), .resumeBatch)
        XCTAssertEqual(inferMWTaskType(from: state(["batch_status": "ready"])), .resumeBatch)
        XCTAssertEqual(inferMWTaskType(from: state(["candidates": [AnyCodable](), "batch_status": "ready"])), .resumeBatch)
    }

    func testOtherMappingsAreUnchanged() {
        XCTAssertEqual(inferMWTaskType(from: state(["candidate_name": "Ada"])), .offerLetter)
        XCTAssertEqual(inferMWTaskType(from: state(["review_title": "H2"])), .review)
        XCTAssertEqual(inferMWTaskType(from: state(["handbook_title": "Handbook"])), .handbook)
        XCTAssertEqual(inferMWTaskType(from: state(["inventory_items": [AnyCodable]()])), .inventory)
        XCTAssertEqual(inferMWTaskType(from: state(["workbook_title": "WB"])), .workbook)
        XCTAssertEqual(inferMWTaskType(from: state(["slides": [AnyCodable]()])), .presentation)
        XCTAssertEqual(inferMWTaskType(from: state(["employees": [AnyCodable]()])), .onboarding)
        XCTAssertEqual(inferMWTaskType(from: [:]), .chat)
    }

    // MARK: - AssetKind

    func testOfferLetterTitleJoinsCandidateAndPosition() {
        let kind = AssetKind(.offerLetter)
        XCTAssertEqual(kind.title(from: state(["candidate_name": "Ada Lovelace", "position_title": "Engineer"])),
                       "Ada Lovelace — Engineer")
        XCTAssertEqual(kind.title(from: state(["position_title": "Engineer"])), "Engineer")
        XCTAssertNil(kind.title(from: state(["candidate_name": "   "])))
    }

    func testDocumentTitlesComeFromTheirOwnKeys() {
        XCTAssertEqual(AssetKind(.policy).title(from: state(["policy_title": " Remote work "])), "Remote work")
        XCTAssertEqual(AssetKind(.presentation).title(from: state(["presentation_title": "Kickoff"])), "Kickoff")
        XCTAssertNil(AssetKind(.onboarding).title(from: state(["employees": [AnyCodable]()])))
    }

    // MARK: - AssetExport

    func testPolicyCopyTextIsItsMarkdown() {
        let markdown = "# Remote work\n\nEveryone may work remotely."
        XCTAssertEqual(AssetExport.copyText(.policy, state: state(["policy_content": markdown])), markdown)
        XCTAssertNil(AssetExport.copyText(.policy, state: state(["policy_content": "  "])))
    }

    func testReviewCopyTextListsEachSection() throws {
        let s = state([
            "review_title": "H2 review",
            "overall_rating": 4,
            "summary": "Strong half.",
            "strengths": [AnyCodable("Ships"), AnyCodable("Mentors")],
            "next_steps": [AnyCodable("Lead the Q1 launch")],
        ])
        let text = try XCTUnwrap(AssetExport.copyText(.review, state: s))
        XCTAssertTrue(text.hasPrefix("# H2 review"))
        XCTAssertTrue(text.contains("Overall rating: 4/5"))
        XCTAssertTrue(text.contains("## Strengths\n- Ships\n- Mentors"))
        XCTAssertTrue(text.contains("## Next steps\n- Lead the Q1 launch"))
        XCTAssertFalse(text.contains("Growth areas"))
    }

    func testNothingToCopyForDocumentsWithoutText() {
        XCTAssertNil(AssetExport.copyText(.offerLetter, state: state(["candidate_name": "Ada"])))
        XCTAssertNil(AssetExport.copyText(.review, state: [:]))
    }

    func testFileNamesDropPathSeparators() {
        XCTAssertEqual(AssetExport.fileSafe("Q4/Q1: plan.pdf"), "Q4-Q1- plan.pdf")
        XCTAssertEqual(AssetExport.fileSafe("   "), "Document")
        XCTAssertEqual(AssetExport.fileSafe(String(repeating: "a", count: 120)).count, 80)
    }

    func testDownloadsNeedSomethingToSave() {
        XCTAssertNil(AssetExport.download(.offerLetter, state: [:], title: "x", threadId: "t", pdfData: nil))
        XCTAssertNotNil(AssetExport.download(.offerLetter, state: [:], title: "x", threadId: "t", pdfData: Data([1])))
        XCTAssertNil(AssetExport.download(.presentation, state: state(["presentation_title": "x"]),
                                          title: "x", threadId: "t", pdfData: nil))
        XCTAssertNotNil(AssetExport.download(.presentation, state: state(["slides": [AnyCodable(["title": AnyCodable("a")])]]),
                                             title: "x", threadId: "t", pdfData: nil))
        XCTAssertNil(AssetExport.download(.policy, state: state(["policy_title": "x"]), title: "x", threadId: "t", pdfData: nil))
    }

    // MARK: - AssetTime

    func testEditedReadsServerTimestamps() throws {
        let now = try XCTUnwrap(AssetTime.parse("2026-10-11T12:00:00Z"))
        XCTAssertEqual(AssetTime.edited("2026-10-11T11:59:40.123Z", now: now), "edited just now")
        XCTAssertNotNil(AssetTime.edited("2026-10-11T11:50:00", now: now))  // naive UTC
        XCTAssertNotNil(AssetTime.edited("2026-10-11T11:50:00.123456", now: now))
        XCTAssertNil(AssetTime.edited("yesterday", now: now))
        XCTAssertNil(AssetTime.edited(nil, now: now))
    }
}
