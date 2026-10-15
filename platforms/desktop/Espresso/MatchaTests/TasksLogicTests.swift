import XCTest
@testable import Matcha

@MainActor
final class TasksLogicTests: XCTestCase {
    private func decode<T: Decodable>(_: T.Type, _ json: String) throws -> T {
        try JSONDecoder().decode(T.self, from: Data(json.utf8))
    }

    // The server's `GET /agent-tasks/{id}`, with a field this build doesn't know.
    private let detailJSON = """
    {"id": "t1", "playbook": "research", "source": "espresso", "engine": "chain", "title": "1bd in SF",
     "directive": "find me a 1bd in SF under 3500 that allows dogs", "brief": {"budget_max": 3500},
     "status": "done", "phase": "summarize", "progress": {"note": "One fits", "found": 6, "shown": 4},
     "error": null, "needs": null, "current_round": 2, "item_count": 6, "shown_count": 4, "input_ids": [],
     "unseen": true, "created_at": "2026-10-14T22:47:51.318250+00:00", "completed_at": null,
     "fingerprint": "abc", "something_new": 1,
     "plan": {"summary": "A 1bd that takes dogs", "item_kind": "listing", "location": "San Francisco",
              "columns": [{"key": "price", "label": "Price", "type": "money"}, {"key": "pets", "label": "Pets", "type": "tags"}],
              "constraints": [{"field": "price", "op": "lte", "value": 3500, "label": "Price at most $3,500/mo"}],
              "preferences": []},
     "rounds": [
        {"id": "r1", "n": 1, "kind": "initial", "directive": "", "status": "done", "units": 3, "items_added": 6,
         "summary": {"headline": "One fits", "summary": "x", "sections": [], "top": [{"item_id": "i1", "why": "Cheapest"}],
                     "counts": {"found": 6, "shown": 4, "hidden": 2}}, "document": null, "error": null},
        {"id": "r2", "n": 2, "kind": "document", "directive": "", "status": "done", "units": 0, "items_added": 0,
         "summary": {}, "document": {"journal_id": "j1", "entry_id": "e1", "title": "Findings", "items": 4}}
     ],
     "items": [
        {"id": "i1", "kind": "listing", "title": "Sunny 1BR", "subtitle": "Mission", "url": "https://apts.test/1",
         "origin": "web", "provider": null, "status": "verified", "fit_score": 4, "rank": 1, "rank_band": 0,
         "flags": [], "user_state": "saved", "round": 1, "images": [{"url": "https://cdn.test/a.webp", "page_url": "p", "alt": ""}],
         "fields": {"price": {"display": "$3,200/mo", "value": 3200, "status": "verified", "unit": "month"},
                    "pets": {"display": "Dogs OK", "value": ["dogs"], "status": "claimed"}}},
        {"id": "i2", "title": "Loft", "rank": 2, "rank_band": 9, "flags": ["violates", "unconfirmed:pets"],
         "user_state": "new", "fields": {}}
     ]}
    """

    func testTheDetailDecodesLeniently() throws {
        let detail = try decode(AgentTaskDetail.self, detailJSON)
        XCTAssertEqual(detail.task.title, "1bd in SF")
        XCTAssertTrue(detail.task.unseen)
        XCTAssertNotNil(detail.task.createdAt)
        XCTAssertEqual(detail.plan.columns.map(\.key), ["price", "pets"])
        XCTAssertEqual(detail.plan.constraints.first?.label, "Price at most $3,500/mo")
        XCTAssertEqual(detail.rounds.map(\.label), ["First search", "Document"])
        XCTAssertEqual(detail.rounds.last?.document?.journalId, "j1")
        XCTAssertEqual(detail.latestSummary?.headline, "One fits")
        XCTAssertEqual(detail.latestSummary?.top.first?.itemId, "i1")
        let first = try XCTUnwrap(detail.items.first)
        XCTAssertEqual(first.fields["price"]?.number, 3200)
        XCTAssertTrue(first.fields["price"]?.isVerified ?? false)
        XCTAssertFalse(first.fields["pets"]?.isVerified ?? true)
        XCTAssertEqual(first.images.first?.pageUrl, "p")
        XCTAssertEqual(detail.visibleItems.map(\.id), ["i1"])
        XCTAssertEqual(detail.hiddenItems.first?.unconfirmed, ["pets"])
        XCTAssertTrue(detail.canFollowUp)
    }

    func testPollReloadsOnlyOnAChange() throws {
        let detail = try decode(AgentTaskDetail.self, detailJSON)
        let same = try decode(AgentTaskStatus.self, #"{"id": "t1", "status": "done", "fingerprint": "abc"}"#)
        let moved = try decode(AgentTaskStatus.self, #"{"id": "t1", "status": "done", "fingerprint": "xyz"}"#)
        let restarted = try decode(AgentTaskStatus.self, #"{"id": "t1", "status": "running", "fingerprint": "abc"}"#)
        XCTAssertFalse(TasksViewModel.changed(detail, same))
        XCTAssertTrue(TasksViewModel.changed(detail, moved))
        XCTAssertTrue(TasksViewModel.changed(detail, restarted))
        XCTAssertEqual(TasksViewModel.pollSeconds(live: true), 4)
        XCTAssertEqual(TasksViewModel.pollSeconds(live: false), 30)
    }

    func testFiltersAndHiddenReasons() throws {
        let items = try decode(AgentTaskDetail.self, detailJSON).items
        XCTAssertEqual(TasksViewModel.filtered(items, filter: .fits).map(\.id), ["i1"])
        XCTAssertEqual(TasksViewModel.filtered(items, filter: .saved).map(\.id), ["i1"])
        XCTAssertEqual(TasksViewModel.filtered(items, filter: .hidden).map(\.id), ["i2"])
        var dismissed = AgentTaskItem(id: "x", title: "X", rankBand: 9, flags: ["unavailable"], userState: "dismissed")
        XCTAssertEqual(dismissed.hiddenReason, "Dismissed")
        dismissed.userState = "new"
        XCTAssertEqual(dismissed.hiddenReason, "No longer available")
        XCTAssertEqual(AgentTaskItem(id: "y", title: "Y", flags: ["irrelevant"]).hiddenReason, "Not a fit")
        XCTAssertNil(AgentTaskItem(id: "z", title: "Z").hiddenReason)
    }

    func testTheListGroupsWhatNeedsThePersonFirst() throws {
        let tasks = [
            AgentTask(id: "a", title: "Done one", status: "done"),
            AgentTask(id: "b", title: "Running one", status: "running"),
            AgentTask(id: "c", title: "Waiting one", status: "waiting"),
            AgentTask(id: "d", title: "Queued one", status: "queued"),
        ]
        let groups = AgentTaskGroup.grouped(tasks)
        XCTAssertEqual(groups.map(\.0), [.needsYou, .running, .done])
        XCTAssertEqual(groups[1].1.map(\.id).sorted(), ["b", "d"])
        XCTAssertEqual(AgentTask(id: "e", title: "", status: "running").statusLabel, "Working…")
        XCTAssertEqual(AgentTask(id: "f", title: "", status: "failed").statusLabel, "Stopped")
        let list = try decode(AgentTaskList.self, #"{"tasks": [{"id": "t", "status": "waiting"}], "usage": {"limit": 60, "used": 29, "remaining": 31, "resets_at": "x"}}"#)
        XCTAssertEqual(TasksViewModel.usageLine(list.usage), "31 of 60 task units left this month")
        XCTAssertNil(TasksViewModel.usageLine(nil))
    }

    func testTheSidebarBadge() {
        XCTAssertTrue(TasksViewModel.badge(nil) == (0, false))
        XCTAssertTrue(TasksViewModel.badge(AgentTasksSummary(running: 2, waiting: 0, unseen: 0)) == (2, false))
        XCTAssertTrue(TasksViewModel.badge(AgentTasksSummary(running: 0, waiting: 1, unseen: 0)) == (0, true))
        XCTAssertTrue(TasksViewModel.badge(AgentTasksSummary(running: 0, waiting: 0, unseen: 3)) == (0, true))
    }

    func testRequestsUseTheServersKeys() throws {
        let round = AgentTaskRoundRequest(requestId: "r", kind: "more", directive: "", itemIds: ["i1"])
        let json = try XCTUnwrap(String(data: JSONEncoder().encode(round), encoding: .utf8))
        XCTAssertTrue(json.contains("\"request_id\":\"r\"") && json.contains("\"item_ids\":[\"i1\"]"))
        let patch = try XCTUnwrap(String(data: JSONEncoder().encode(AgentTaskItemPatch(userState: "saved")), encoding: .utf8))
        XCTAssertEqual(patch, #"{"user_state":"saved"}"#)
    }

    // MARK: Forms and cards in chat

    private let formPromptJSON = """
    {"kind": "agent_card_prompt", "prompt_kind": "ask_form", "prompt_id": "p1", "owner_user_id": "u1",
     "expires_at": "2026-10-16T00:00:00+00:00",
     "view": {"question": "Where should I look?", "buttons": [],
              "form": {"playbook": "research", "label": "Research", "title": "1bd", "directive": "find a 1bd",
                       "fields": [{"key": "location", "label": "Where", "type": "location", "required": true, "ask": "if_missing", "help": ""},
                                  {"key": "budget_max", "label": "Budget (max)", "type": "money", "optional": true, "value": 3500},
                                  {"key": "must_haves", "label": "Must have", "type": "list"},
                                  {"key": "reference_files", "label": "Files", "type": "file", "accept": ["image", "document"], "max_count": 3, "max_bytes": 10485760}],
                       "known": [{"key": "pets", "label": "Pets", "value": ["dogs"], "shown": "dogs"}],
                       "consent": null, "units": 3, "submit_label": "Start"}}}
    """

    func testAFormPromptDecodesAndRoundTrips() throws {
        let meta = try decode(ChannelMessageMetadata.self, formPromptJSON)
        XCTAssertTrue(meta.isAgentCard)
        XCTAssertTrue(meta.isAssistantPrompt)
        let form = try XCTUnwrap(meta.view?.form)
        XCTAssertEqual(form.fields.map(\.key), ["location", "budget_max", "must_haves", "reference_files"])
        XCTAssertEqual(form.fields[1].initial, "3500")
        XCTAssertTrue(form.fields[1].optional)
        XCTAssertEqual(form.fields[3].maxCount, 3)
        XCTAssertEqual(form.known.first?.shown, "dogs")
        XCTAssertEqual(form.units, 3)
        // Message metadata is re-encoded as a whole: the form survives it.
        let again = try JSONDecoder().decode(ChannelMessageMetadata.self, from: JSONEncoder().encode(meta))
        XCTAssertEqual(again.view?.form, form)
    }

    func testFormValuesBecomeWhatTheServerTakes() throws {
        let form = try XCTUnwrap(try decode(ChannelMessageMetadata.self, formPromptJSON).view?.form)
        var built = IntakeFormValues.build(form.fields, text: [:])
        XCTAssertEqual(built.problems, [.missing("Where")])
        built = IntakeFormValues.build(form.fields, text: ["location": " SF ", "budget_max": "$3.5k",
                                                          "must_haves": "dogs, laundry,"])
        XCTAssertTrue(built.problems.isEmpty)
        XCTAssertEqual(built.values["location"]?.value as? String, "SF")
        XCTAssertEqual(built.values["budget_max"]?.value as? Double, 3500)
        XCTAssertEqual((built.values["must_haves"]?.value as? [AnyCodable])?.compactMap { $0.value as? String },
                       ["dogs", "laundry"])
        built = IntakeFormValues.build(form.fields, text: ["location": "SF", "budget_max": "lots"])
        XCTAssertEqual(built.problems, [.invalid("Budget (max)")])
        XCTAssertEqual(IntakeFormValues.Problem.invalid("Budget").message, "Budget doesn't look right.")
        let more = [IntakeFormField(key: "d", label: "Date", type: "date"),
                    IntakeFormField(key: "t", label: "Time", type: "time"),
                    IntakeFormField(key: "b", label: "Dogs", type: "boolean"),
                    IntakeFormField(key: "s", label: "Size", type: "select", options: ["S", "M"]),
                    IntakeFormField(key: "f", label: "Photo", type: "file", required: true)]
        built = IntakeFormValues.build(more, text: ["d": "2026-12-01", "t": "7:05", "b": "yes", "s": "M"],
                                       files: ["f": ["a.png"]])
        XCTAssertTrue(built.problems.isEmpty)
        XCTAssertEqual(built.values["t"]?.value as? String, "07:05")
        XCTAssertEqual(built.values["b"]?.value as? Bool, true)
        built = IntakeFormValues.build(more, text: ["d": "Dec 1", "t": "25:00", "b": "maybe", "s": "XL"])
        XCTAssertEqual(built.problems, [.invalid("Date"), .invalid("Time"), .invalid("Dogs"), .invalid("Size"),
                                        .missing("Photo")])
        let answer = IntakeFormAnswer(values: ["location": AnyCodable("SF")], inputIds: ["in1"], consentVersion: nil)
        let json = try XCTUnwrap(String(data: JSONEncoder().encode(answer), encoding: .utf8))
        XCTAssertTrue(json.contains("\"input_ids\":[\"in1\"]") && json.contains("\"location\":\"SF\""))
        XCTAssertEqual(IntakeFormCard.placeholder(form.fields[1]), "$3,500")
        XCTAssertFalse(IntakeFormCard.contentTypes(["image"]).isEmpty)
    }

    func testATaskCardAndATaskBlock() throws {
        let card = """
        {"kind": "agent_task", "task_id": "t1",
         "task": {"event": "update", "task_id": "t1", "playbook": "research", "title": "1bd in SF", "status": "done",
                  "note": "", "headline": "One fits", "counts": {"found": 6},
                  "items": [{"id": "i1", "title": "Sunny 1BR", "subtitle": "Mission", "url": "https://apts.test/1",
                             "fields": {"price": "$3,200/mo"}, "image": null}]}}
        """
        let meta = try decode(ChannelMessageMetadata.self, card)
        XCTAssertTrue(meta.isAgentCard)
        let task = try XCTUnwrap(meta.task)
        XCTAssertEqual(TaskChatText.lead(task), "Task done")
        XCTAssertEqual(TaskChatText.body(task), "One fits")
        XCTAssertEqual(task.items.first?.fields["price"], "$3,200/mo")
        let result = """
        {"headline": "h", "summary": "s", "blocks": [{"type": "task", "task": {"event": "update", "task_id": "t1",
          "title": "x", "status": "running", "note": "Reading", "items": []}}, {"type": "brand_new"}]}
        """
        let decoded = try decode(AgentChatResultV2.self, result)
        guard case .task(let block) = decoded.blocks.first else { return XCTFail("no task block") }
        XCTAssertEqual(block.taskId, "t1")
        let again = try JSONDecoder().decode(AgentChatResultV2.self, from: JSONEncoder().encode(decoded))
        XCTAssertEqual(again, decoded)
    }

    func testCardWordsForEachEnd() throws {
        func card(_ event: String, _ status: String, note: String = "", headline: String? = nil) throws -> AgentTaskCard {
            let head = headline.map { "\"\($0)\"" } ?? "null"
            return try decode(AgentTaskCard.self, """
            {"event": "\(event)", "task_id": "t", "title": "x", "status": "\(status)", "note": "\(note)", "headline": \(head)}
            """)
        }
        XCTAssertEqual(TaskChatText.lead(try card("started", "queued")), "Started a task")
        XCTAssertEqual(TaskChatText.lead(try card("update", "failed")), "Task stopped")
        XCTAssertEqual(TaskChatText.lead(try card("update", "waiting")), "Task needs you")
        XCTAssertEqual(TaskChatText.icon(try card("update", "done")), "checkmark.circle.fill")
        XCTAssertNil(TaskChatText.body(try card("update", "failed")))
        XCTAssertEqual(TaskChatText.body(try card("update", "failed", note: "Nothing matched")), "Nothing matched")
    }

    func testFactsShowInThePlansOrder() {
        let item = AgentTaskItem(id: "i", title: "X", fields: [
            "rating": AgentTaskField(display: "4.6"), "price": AgentTaskField(display: "$3"),
            "beds": AgentTaskField(display: "1")])
        let columns = [AgentTaskColumn(key: "price", label: "Price", type: "money"),
                       AgentTaskColumn(key: "pets", label: "Pets", type: "tags")]
        XCTAssertEqual(TaskItemDetailView.factOrder(item, columns: columns), ["price", "beds", "rating"])
        XCTAssertEqual(TaskItemDetailView.label(for: "review_count"), "Review Count")
    }

    func testEntitlementsCarryTheTasksFlag() throws {
        let flags = try decode(MWWorkspaceFlags.self, #"{"espresso_assistant": true, "agent_tasks": true}"#)
        XCTAssertEqual(flags.agentTasks, true)
        XCTAssertNil(try decode(MWWorkspaceFlags.self, #"{"espresso_assistant": true}"#).agentTasks)
    }

    func testAJobSearchIsATask() throws {
        let json = """
        {"id": "t9", "playbook": "job_search", "engine": "job_search", "job_search_id": "s1",
         "title": "COO", "directive": "COO roles", "status": "running", "phase": "discovering",
         "progress": {"note": "Searching"}, "current_round": 0, "item_count": 12, "shown_count": 9,
         "unseen": false, "created_at": "2026-10-15T01:00:00+00:00", "fingerprint": "fp",
         "plan": {"columns": [], "constraints": [], "preferences": [], "summary": ""}, "rounds": [],
         "items": [], "job_search": {"id": "s1"}}
        """
        let detail = try decode(AgentTaskDetail.self, json)
        XCTAssertTrue(detail.task.isJobSearch)
        XCTAssertEqual(detail.task.jobSearchId, "s1")
        XCTAssertEqual(detail.task.statusLabel, "Searching…")
        // Refined and redrafted on its own page, not with Tasks' rounds.
        XCTAssertFalse(detail.canFollowUp)
        XCTAssertFalse(try decode(AgentTaskDetail.self, detailJSON).task.isJobSearch)

        var search = AgentTask(id: "t9", title: "COO", status: "done")
        XCTAssertNil(TasksViewModel.task(forSearch: "s1", in: [search]))
        search.engine = "job_search"; search.jobSearchId = "s1"
        XCTAssertEqual(TasksViewModel.task(forSearch: "s1", in: [AgentTask(id: "t1", title: "x", status: "done"), search])?.id,
                       "t9")
        XCTAssertNil(TasksViewModel.task(forSearch: "s2", in: [search]))
        for (phase, label) in [("planning", "Planning…"), ("screening", "Checking what fits…"),
                               ("enriching", "Reading postings…"), ("approaching", "Drafting approaches…")] {
            var task = search; task.status = "running"; task.phase = phase
            XCTAssertEqual(task.statusLabel, label)
        }
    }

    func testAJobSearchOpensInTasks() {
        let focus = TasksFocus(taskId: nil, jobSearchId: "s1", leadId: "l1")
        XCTAssertNil(focus.taskId)
        XCTAssertEqual(focus.leadId, "l1")
        XCTAssertEqual(TasksFocus(taskId: "t1", itemId: "i1"), TasksFocus(taskId: "t1", itemId: "i1", jobSearchId: nil))
    }

    func testTasksIsAFixedRow() {
        // Tasks is a fixed row under the Espresso card, not a section that moves.
        XCTAssertNil(SidebarSectionOrderStore.Section(rawValue: "tasks"))
        XCTAssertEqual(FeatureGuide.guide(for: .tasks).name, "Tasks")
    }

    func testAHandoffDraftsTheDirectiveOrAQuestion() {
        let start = AssistantTaskContext(owner: "u", directive: "find a lamp", taskId: nil, itemId: nil)
        XCTAssertEqual(start.prompt, "find a lamp")
        XCTAssertEqual(start.conversationTitle, "Task: find a lamp")
        let about = AssistantTaskContext(owner: "u", directive: "", taskId: "t1", itemId: "i1")
        XCTAssertTrue(about.prompt.contains("finding i1 in my task t1"))
        XCTAssertEqual(about.conversationTitle, "About a task")
        XCTAssertTrue(AssistantTaskContext(owner: "u", directive: "", taskId: "t1", itemId: nil).prompt
            .contains("my task t1"))
    }

    func testALinkIsNamedForItsSiteOrGooglesPart() throws {
        func label(_ s: String) throws -> String { TasksViewModel.linkLabel(try XCTUnwrap(URL(string: s))) }
        XCTAssertEqual(try label("https://www.drbronner.com/products/balm?utm_source=goog"), "drbronner.com")
        XCTAssertEqual(try label("https://shop.sprouts.com/landing"), "shop.sprouts.com")
        XCTAssertEqual(try label("https://www.google.com/search?ibp=oshop&q=balm&prds=productid:1"), "Google Shopping")
        // As stored from the provider: spaces and bars in the query.
        XCTAssertEqual(try label("https://www.google.com/search?ibp=oshop&q=organic lip balm&prds=rds:PC_1|PROD_PC_1"),
                       "Google Shopping")
        XCTAssertEqual(try label("https://www.google.com/shopping/product/545"), "Google Shopping")
        XCTAssertEqual(try label("https://www.google.com/maps/search/?api=1&query=Ramen"), "Google Maps")
        XCTAssertEqual(try label("https://www.google.com/search?q=balm"), "google.com")
    }
}
