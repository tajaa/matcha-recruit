import XCTest
@testable import Matcha

/// Job search's client rules: decoding the server's shapes (old and new),
/// when the poll reloads, filtering, pay lines, safe links, and the assistant's
/// `jobs` block. No network, no signed-in session.
@MainActor
final class JobSearchLogicTests: XCTestCase {

    private func decode<T: Decodable>(_ type: T.Type, _ json: String) throws -> T {
        try JSONDecoder().decode(T.self, from: Data(json.utf8))
    }

    private let detailJSON = """
    {"id": "s1", "title": "COO", "ask": "COO roles across the US", "status": "enriching",
     "progress": {"note": "Reading 24 postings", "found": 40, "extra": [1, 2]},
     "weights": {"base": 0.45, "bonus": 0.2, "equity": 0.2, "fit": 0.15},
     "lead_count": 2, "posted_pay_count": 1, "use_resume": true, "fingerprint": "abc",
     "leads": [
       {"id": "l1", "title": "COO", "company": "Acme", "location": "Austin, TX", "remote": false,
        "comp_line": "$250K–$300K · 30% bonus", "comp_status": "posted", "comp_annual_min": 250000,
        "comp_annual_max": 300000, "bonus_pct": 30, "fit_score": 4, "screen_status": "relevant",
        "rank": 1, "rank_band": 0, "flags": [], "user_state": "saved", "approach_status": "done",
        "apply_url": "https://boards.greenhouse.io/acme/jobs/1"},
       {"id": "l2", "title": "COO", "company": "Beta", "location": "Remote", "comp_status": "not_disclosed",
        "screen_status": "irrelevant", "rank": 2, "user_state": "new", "approach_status": "queued",
        "something_new": true}
     ]}
    """

    func testDetailDecodesLeniently() throws {
        let detail = try decode(JobSearchDetail.self, detailJSON)
        XCTAssertEqual(detail.search.id, "s1")
        XCTAssertTrue(detail.search.isLive)
        XCTAssertEqual(detail.search.progress.note, "Reading 24 postings")
        XCTAssertEqual(detail.search.progress.found, 40)
        XCTAssertEqual(detail.leads.count, 2)
        XCTAssertEqual(detail.leads[0].bonusPct, 30)
        // A lead missing fields still decodes, with safe defaults.
        XCTAssertEqual(detail.leads[1].compLine, "Pay not posted")
        XCTAssertTrue(detail.leads[1].isIrrelevant)
        XCTAssertTrue(detail.leads[1].isDrafting)
        XCTAssertNil(detail.leads[1].fitScore)
    }

    func testPollReloadsOnlyOnAChange() throws {
        let detail = try decode(JobSearchDetail.self, detailJSON)
        let same = try decode(JobSearchStatusView.self,
                              #"{"id": "s1", "status": "enriching", "lead_count": 2, "fingerprint": "abc"}"#)
        XCTAssertFalse(JobSearchViewModel.changed(detail, same))
        let moved = try decode(JobSearchStatusView.self,
                               #"{"id": "s1", "status": "approaching", "lead_count": 2, "fingerprint": "abc"}"#)
        XCTAssertTrue(JobSearchViewModel.changed(detail, moved))
        let progressed = try decode(JobSearchStatusView.self,
                                    #"{"id": "s1", "status": "enriching", "lead_count": 2, "fingerprint": "xyz"}"#)
        XCTAssertTrue(JobSearchViewModel.changed(detail, progressed))
    }

    func testFilters() throws {
        let leads = try decode(JobSearchDetail.self, detailJSON).leads
        XCTAssertEqual(JobSearchViewModel.filtered(leads, filter: .all, showIrrelevant: false).map(\.id), ["l1"])
        XCTAssertEqual(JobSearchViewModel.filtered(leads, filter: .all, showIrrelevant: true).map(\.id), ["l1", "l2"])
        XCTAssertEqual(JobSearchViewModel.filtered(leads, filter: .postedPay, showIrrelevant: true).map(\.id), ["l1"])
        XCTAssertEqual(JobSearchViewModel.filtered(leads, filter: .saved, showIrrelevant: false).map(\.id), ["l1"])
        XCTAssertTrue(JobSearchViewModel.filtered(leads, filter: .applied, showIrrelevant: true).isEmpty)
    }

    func testDraftedShowsTheJobsWithAnApproach() throws {
        var leads = try decode(JobSearchDetail.self, detailJSON).leads
        XCTAssertEqual(JobSearchViewModel.filtered(leads, filter: .drafted, showIrrelevant: false).map(\.id), ["l1"])
        leads[0].userState = "dismissed"
        XCTAssertTrue(JobSearchViewModel.filtered(leads, filter: .drafted, showIrrelevant: false).isEmpty)
        XCTAssertEqual(JobSearchViewModel.Filter.allCases.first, .all)
        XCTAssertEqual(JobSearchViewModel.Filter.drafted.rawValue, "Drafted")
    }

    func testAJobsEmailStateAndTheSearchsProgress() throws {
        let json = """
        {"id": "s1", "status": "done", "fingerprint": "f", "leads": [
          {"id": "a", "approach_status": "done", "user_state": "saved", "email_draft_id": "r-1",
           "email_drafted_at": "2026-10-15T03:00:00+00:00", "email_sent_at": null},
          {"id": "b", "approach_status": "done", "user_state": "applied", "email_draft_id": "r-2",
           "email_sent_at": "2026-10-15T04:00:00+00:00"},
          {"id": "c", "approach_status": "done", "user_state": "dismissed", "email_draft_id": "r-3"},
          {"id": "d", "approach_status": "done", "screen_status": "irrelevant"},
          {"id": "e", "approach_status": "none"}
        ]}
        """
        let leads = try decode(JobSearchDetail.self, json).leads
        XCTAssertTrue(leads[0].emailWaiting)
        XCTAssertNotNil(leads[0].emailDraftedAt)
        XCTAssertFalse(leads[1].emailWaiting)
        XCTAssertNotNil(leads[1].emailSentAt)
        XCTAssertNil(leads[4].emailDraftId)
        let progress = JobSearchViewModel.progress(leads)
        // Dismissed jobs don't count; a screened-out job with an approach isn't one to read.
        XCTAssertEqual(progress, JobSearchViewModel.Progress(drafted: 2, saved: 1, emailsWaiting: 1, emailsSent: 1, applied: 1))
        XCTAssertEqual(progress.line, "1 saved · 1 email in drafts · 1 sent · 1 applied")
        XCTAssertNil(JobSearchViewModel.Progress().line)
        XCTAssertEqual(JobSearchViewModel.Progress(emailsWaiting: 2).line, "2 emails in drafts")

        XCTAssertEqual(JobSearchDetailView.statusText(leads[0]), "In drafts")
        XCTAssertEqual(JobSearchDetailView.statusText(leads[1]), "Applied")
        XCTAssertEqual(JobSearchDetailView.statusText(leads[3]), "Screened out")
        XCTAssertEqual(JobSearchDetailView.statusText(leads[4]), "")
        var sent = leads[0]
        sent.emailSentAt = Date()
        XCTAssertEqual(JobSearchDetailView.statusText(sent), "Emailed")

        let result = try decode(JobEmailDraftResult.self, #"{"draft_id": "r-9", "to": "", "subject": "COO at Acme", "created": true}"#)
        XCTAssertEqual(result.draftId, "r-9")
        XCTAssertTrue(result.created)
        XCTAssertNil(result.lead)
    }

    func testTheListGoesCompactBesideAJobOrWhenNarrow() throws {
        let wide = JobSearchDetailView.fullTableWidth + 200
        XCTAssertFalse(JobSearchDetailView.usesCompactList(leadOpen: false, width: wide))
        XCTAssertTrue(JobSearchDetailView.usesCompactList(leadOpen: true, width: wide))
        XCTAssertTrue(JobSearchDetailView.usesCompactList(leadOpen: false, width: JobSearchDetailView.fullTableWidth - 1))
        XCTAssertLessThan(JobSearchDetailView.minContentWidth, JobSearchDetailView.fullTableWidth)

        let json = """
        {"id": "s1", "status": "done", "fingerprint": "f", "leads": [
          {"id": "a", "company": "Flex", "location": "New York, NY", "remote": true},
          {"id": "b", "company": "Acme", "location": "Remote (US)", "remote": true},
          {"id": "c", "company": "Initech", "location": ""}
        ]}
        """
        let leads = try decode(JobSearchDetail.self, json).leads
        XCTAssertEqual(JobSearchDetailView.companyLine(leads[0]), "Flex · New York, NY · Remote")
        XCTAssertEqual(JobSearchDetailView.companyLine(leads[1]), "Acme · Remote (US)")
        XCTAssertEqual(JobSearchDetailView.companyLine(leads[2]), "Initech")
        XCTAssertTrue(JobSearchDetailView.showsRemoteBadge(leads[0]))
        XCTAssertFalse(JobSearchDetailView.showsRemoteBadge(leads[1]))
    }

    func testAPostingReadsCleanly() {
        let raw = "Chief Operating Officer (COFO)\n  Backpack Healthcare | Hybrid\n\n\n\u{00A0} Build the  engine\r\n\n\n  We are   growing.\n\n"
        XCTAssertEqual(JobSearchViewModel.tidyPosting(raw),
                       "Chief Operating Officer (COFO)\nBackpack Healthcare | Hybrid\n\nBuild the engine\n\nWe are growing.")
        XCTAssertEqual(JobSearchViewModel.tidyPosting("\n\n  \n"), "")
    }

    func testJobsYouSavedOrAppliedToStayInThoseTabsEvenIfScreenedOut() throws {
        var leads = try decode(JobSearchDetail.self, detailJSON).leads
        leads[1].userState = "applied"  // l2 is screened out
        XCTAssertEqual(JobSearchViewModel.filtered(leads, filter: .applied, showIrrelevant: false).map(\.id), ["l2"])
        leads[1].userState = "saved"
        XCTAssertEqual(JobSearchViewModel.filtered(leads, filter: .saved, showIrrelevant: false).map(\.id), ["l1", "l2"])
        XCTAssertEqual(JobSearchViewModel.filtered(leads, filter: .all, showIrrelevant: false).map(\.id), ["l1"])
    }

    func testMinimumBaseReadsWhatPeopleType() {
        typealias C = JobSearchCriteria
        XCTAssertEqual(C.parseBaseFloor(""), .none)
        XCTAssertEqual(C.parseBaseFloor("  "), .none)
        XCTAssertEqual(C.parseBaseFloor("250000"), .amount(250_000))
        XCTAssertEqual(C.parseBaseFloor("250,000"), .amount(250_000))
        XCTAssertEqual(C.parseBaseFloor("$250,000.00"), .amount(250_000))
        XCTAssertEqual(C.parseBaseFloor("250k"), .amount(250_000))
        XCTAssertEqual(C.parseBaseFloor("$250K"), .amount(250_000))
        XCTAssertEqual(C.parseBaseFloor("1.5M"), .amount(1_500_000))
        XCTAssertEqual(C.parseBaseFloor("1.5 mm"), .amount(1_500_000))
        XCTAssertEqual(C.parseBaseFloor("250000 USD"), .amount(250_000))
        XCTAssertEqual(C.parseBaseFloor("lots"), .invalid)
        XCTAssertEqual(C.parseBaseFloor("250-300k"), .invalid)
        XCTAssertEqual(C.parseBaseFloor("1.2.3"), .invalid)
        XCTAssertEqual(C.parseBaseFloor("20M"), .invalid, "more than the server's $10M ceiling")
        XCTAssertEqual(JobSearchViewModel.dollars(250_000), "$250,000")
    }

    func testOnlyARefusalMakesARetryANewRequest() {
        XCTAssertTrue(JobSearchViewModel.retryIsNewRequest(APIError.httpError(409, "already running")))
        XCTAssertTrue(JobSearchViewModel.retryIsNewRequest(APIError.httpError(429, "limit")))
        XCTAssertTrue(JobSearchViewModel.retryIsNewRequest(APIError.httpError(503, "couldn't queue")))
        XCTAssertFalse(JobSearchViewModel.retryIsNewRequest(APIError.networkUnavailable(URLError(.timedOut))))
        XCTAssertFalse(JobSearchViewModel.retryIsNewRequest(APIError.serviceUnavailable(504)))
        XCTAssertFalse(JobSearchViewModel.retryIsNewRequest(APIError.httpError(500, "boom")))
        XCTAssertFalse(JobSearchViewModel.retryIsNewRequest(URLError(.networkConnectionLost)))
    }

    func testDraftingIsOfferedOnlyWhereTheServerAllowsIt() throws {
        var search = try decode(JobSearchDetail.self, detailJSON).search
        for (status, allowed) in [("done", true), ("cancelled", true), ("failed", false), ("enriching", false)] {
            search.status = status
            XCTAssertEqual(search.canDraft, allowed, status)
        }
    }

    func testResumeFileTypes() {
        XCTAssertEqual(JobSearchService.mimeType(for: "cv.pdf"), "application/pdf")
        XCTAssertEqual(JobSearchService.mimeType(for: "CV.DOCX"),
                       "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        XCTAssertEqual(JobSearchService.mimeType(for: "notes.txt"), "text/plain")
        XCTAssertEqual(JobSearchService.mimeType(for: "mystery"), "application/octet-stream")
        XCTAssertEqual(JobSearchService.resumeTypes.count, 4)
    }

    func testLeadDetailWithEvidenceAndApproach() throws {
        let lead = try decode(JobLeadDetail.self, """
        {"id": "l1", "title": "COO", "company": "Acme", "location": "Austin, TX",
         "comp_line": "$250K–$300K", "comp_status": "posted", "screen_status": "relevant",
         "user_state": "new", "approach_status": "done", "description": "Run ops.",
         "comp": {"base": {"status": "posted", "min": 250000, "max": 300000, "currency": "USD", "period": "year",
                           "annual_min": 250000, "annual_max": 300000,
                           "evidence": {"quote": "The base salary range is $250,000 - $300,000",
                                        "origin": "ats_api", "url": "https://boards.greenhouse.io/acme/jobs/1"}},
                  "bonus": {"status": "posted", "kind": "annual", "pct_min": 30, "pct_max": 30}},
         "ats": {"provider": "greenhouse", "questions": [{"key": "q1", "label": "Why us?", "kind": "open"}]},
         "pay_law_hint": null, "fit_reasons": ["Right level"], "notes": "",
         "approach": {"summary": "Write to Dana.", "channel": "hiring_manager", "steps": ["Apply"],
                      "contacts": [{"name": "Dana Ruiz", "role": "CEO", "source_url": "https://acme.test/team"}],
                      "outreach": {"to_email": "dana@acme.test", "subject": "COO", "body": "Hi Dana"},
                      "answers": [{"question_key": "q1", "question": "Why us?", "answer": "Because", "likely": false}],
                      "unanswered": [{"question_key": "q2", "question": "Authorized to work?", "kind": "authorization"}],
                      "cover_letter": "Dear Acme", "sources": []}}
        """)
        XCTAssertEqual(lead.comp.parts.map(\.0), ["Base", "Bonus"])
        XCTAssertEqual(lead.comp.base?.evidence?.originLabel, "From the job board's data")
        XCTAssertEqual(lead.approach?.channelLabel, "Hiring manager")
        XCTAssertEqual(lead.approach?.contacts.first?.name, "Dana Ruiz")
        XCTAssertEqual(lead.approach?.unanswered.first?.text, "Authorized to work?")
        XCTAssertEqual(lead.ats?.questions.first?.text, "Why us?")

        // An empty approach object is no approach.
        let bare = try decode(JobLeadDetail.self, #"{"id": "l2", "approach": {}}"#)
        XCTAssertNil(bare.approach)
        XCTAssertTrue(bare.comp.parts.isEmpty)
    }

    func testPayLines() {
        let base = JobCompPart(status: "posted", min: 250_000, max: 300_000, currency: "USD", period: "year")
        XCTAssertEqual(JobSearchViewModel.partLine("Base", base), "$250,000–$300,000 a year")
        let hourly = JobCompPart(status: "posted", min: 85, max: 85, currency: "USD", period: "hour")
        XCTAssertEqual(JobSearchViewModel.partLine("Base", hourly), "$85 an hour")
        let bonus = JobCompPart(status: "posted", pctMin: 20, pctMax: 30)
        XCTAssertEqual(JobSearchViewModel.partLine("Bonus", bonus), "20–30% of base")
        let equity = JobCompPart(status: "posted", pctMin: 0.5, pctMax: 1)
        XCTAssertEqual(JobSearchViewModel.partLine("Equity", equity), "0.5–1%")
        // Like the server's pay line: never "12%" for 12.5% or an exponent.
        XCTAssertEqual(JobSearchViewModel.partLine("Bonus", JobCompPart(status: "posted", pctMin: 12.5)), "12.5% of base")
        XCTAssertEqual(JobSearchViewModel.partLine("Equity", JobCompPart(status: "posted", pctMin: 1.25)), "1.25%")
        XCTAssertEqual(JobSearchViewModel.partLine("Bonus", JobCompPart(status: "posted", pctMin: 112.5)), "112.5% of base")
        XCTAssertEqual(JobSearchViewModel.trim(0.125), "0.125")
        XCTAssertEqual(JobSearchViewModel.partLine("Equity", JobCompPart(status: "mentioned")), "Mentioned, no figure")
        XCTAssertEqual(JobSearchViewModel.compBadge("posted"), "Posted")
        XCTAssertEqual(JobSearchViewModel.compBadge("not_disclosed"), "Not posted")
        XCTAssertEqual(JobSearchViewModel.fitText(4), "4/5")
        XCTAssertEqual(JobSearchViewModel.fitText(nil), "\u{2013}")
    }

    func testLinksAreSafe() {
        XCTAssertNotNil(JobSearchViewModel.webURL("https://boards.greenhouse.io/acme/jobs/1"))
        XCTAssertNil(JobSearchViewModel.webURL("javascript:alert(1)"))
        XCTAssertNil(JobSearchViewModel.webURL("file:///etc/passwd"))
        XCTAssertNil(JobSearchViewModel.webURL(nil))
    }

    func testCriteriaAndPhases() {
        XCTAssertEqual(JobSearchCriteria.split("COO, Chief Operating Officer; coo\n President "),
                       ["COO", "Chief Operating Officer", "President"])
        XCTAssertEqual(JobSearchPhase.from(status: "discovering"), .searching)
        XCTAssertEqual(JobSearchPhase.from(status: "approaching"), .drafting)
        XCTAssertNil(JobSearchPhase.from(status: "failed"))
        XCTAssertEqual(JobSearchStatus.label("enriching"), "Reading postings")
        XCTAssertFalse(JobSearchStatus.isLive("done"))
        XCTAssertEqual(JobSearchViewModel.usageLine(MWRunQuota(limit: 4, used: 1, remaining: 3, resetsAt: nil)),
                       "3 of 4 searches left this month")
        XCTAssertNil(JobSearchViewModel.usageLine(MWRunQuota(limit: 0, used: 0, remaining: 0, resetsAt: nil)))
    }

    func testCreateBodyUsesTheServersKeys() throws {
        var criteria = JobSearchCriteria()
        criteria.titles = ["COO"]
        criteria.baseFloor = 250_000
        let body = JobSearchService.CreateBody(requestId: UUID(), title: "COO", ask: "COO roles", criteria: criteria,
                                               weights: nil, useResume: true, consentVersion: "jobs-1")
        let json = try JSONSerialization.jsonObject(with: JSONEncoder().encode(body)) as? [String: Any]
        XCTAssertEqual(json?["use_resume"] as? Bool, true)
        XCTAssertEqual(json?["consent_version"] as? String, "jobs-1")
        XCTAssertNotNil(json?["request_id"])
        let sent = json?["criteria"] as? [String: Any]
        XCTAssertEqual(sent?["base_floor"] as? Int, 250_000)
        XCTAssertEqual(sent?["remote"] as? String, "any")
    }

    func testListAndResumeDecode() throws {
        let list = try decode(JobSearchList.self, """
        {"searches": [], "usage": {"limit": 4, "used": 0, "remaining": 4, "resets_at": "2026-11-01T00:00:00+00:00"},
         "consent": {"granted": false, "disclosure": {"version": "jobs-1", "title": "T", "body": ["a"]}},
         "available": true}
        """)
        XCTAssertEqual(list.usage?.remaining, 4)
        XCTAssertEqual(list.consent?.disclosure?.version, "jobs-1")
        let resume = try decode(ProfileResume.self, """
        {"filename": "cv.pdf", "resume_url": "x", "updated_at": "2026-10-01",
         "parsed_data": {"current_title": "VP Operations", "skills": ["Ops"]}}
        """)
        XCTAssertEqual(resume.currentTitle, "VP Operations")
        let noParsed = try decode(ProfileResume.self, #"{"filename": "cv.pdf", "parsed_data": {}}"#)
        XCTAssertNil(noParsed.currentTitle)
    }

    func testAssistantJobsBlockRoundTrips() throws {
        let json = """
        {"headline": "Your top COO roles", "summary": "", "blocks": [
          {"type": "jobs", "search_id": "s1", "jobs": [
            {"id": "l1", "rank": 1, "title": "COO", "company": "Acme", "location": "Austin, TX",
             "comp_line": "$250K–$300K", "comp_status": "posted", "fit_score": 4, "user_state": "saved",
             "apply_url": "https://boards.greenhouse.io/acme/jobs/1"}]},
          {"type": "something_newer"}
        ]}
        """
        let result = try decode(AgentChatResultV2.self, json)
        guard case .jobs(let block) = result.blocks.first else { return XCTFail("expected a jobs block") }
        XCTAssertEqual(block.searchId, "s1")
        XCTAssertEqual(block.jobs.first?.compLine, "$250K–$300K")
        guard case .unknown(let type) = result.blocks.last else { return XCTFail("expected unknown") }
        XCTAssertEqual(type, "something_newer")
        let again = try JSONDecoder().decode(AgentChatResultV2.self, from: JSONEncoder().encode(result))
        XCTAssertEqual(again.blocks, result.blocks)
    }

    func testJobSearchLivesInTasksNow() {
        // A saved sidebar order that still names the old section just drops it.
        XCTAssertNil(SidebarSectionOrderStore.Section(rawValue: "jobs"))
        XCTAssertFalse(SidebarSectionOrderStore.Section.allCases.map(\.rawValue).contains("jobs"))
        // Its guide stays, opened from the search itself.
        XCTAssertEqual(FeatureGuide.guide(for: .jobSearch).name, "Job search")
    }
}
