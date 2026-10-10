import XCTest
@testable import MatchaSchedule

final class ManagerTests: XCTestCase {
    private let scopeJSON = """
    {"can_manage":true,"role":"employee","company_wide":false,
     "locations":[{"id":"loc-a","name":"Downtown","timezone":"America/Los_Angeles","week_start_weekday":1}],
     "features":{"huume":true,"matcha_work":true,"time_off":false},"pending_requests":3}
    """

    private func scope(companyWide: Bool = false) throws -> ManagerScope {
        let json = companyWide
            ? scopeJSON.replacingOccurrences(of: "\"company_wide\":false", with: "\"company_wide\":true")
            : scopeJSON
        return try JSONDecoder().decode(ManagerScope.self, from: Data(json.utf8))
    }

    private func employee() throws -> EmployeeProfile {
        let json = """
        {"id":"emp-1","company_name":"Po Coffee Co","first_name":"Maria","last_name":"Rossi",
         "enabled_features":{"employee_schedule":true,"time_off":true}}
        """
        return try JSONDecoder().decode(EmployeeProfile.self, from: Data(json.utf8))
    }

    // MARK: Sign-in shapes

    func testMeDecodesAnEmployeeAndABusinessAdmin() throws {
        let crew = """
        {"user":{"id":"u1","email":"maria@example.com","role":"employee"},
         "profile":{"id":"emp-1","company_name":"Po Coffee Co","first_name":"Maria","last_name":"Rossi",
                    "enabled_features":{"employee_schedule":true,"time_off":false}}}
        """
        let me = try JSONDecoder().decode(MeResponse.self, from: Data(crew.utf8))
        XCTAssertEqual(me.profile?.displayName, "Maria Rossi")
        XCTAssertNil(me.business)

        // A client's profile has `name`, not first/last: it must not fail the decode.
        let admin = """
        {"user":{"id":"u2","email":"owner@example.com","role":"client"},
         "profile":{"company_id":"c1","company_name":"Po Coffee Co","name":"Jordan Owner",
                    "enabled_features":{"employee_schedule":true},"is_personal":false}}
        """
        let business = try JSONDecoder().decode(MeResponse.self, from: Data(admin.utf8))
        XCTAssertNil(business.profile)
        XCTAssertEqual(business.business?.name, "Jordan Owner")
        XCTAssertEqual(business.business?.company_name, "Po Coffee Co")
    }

    func testScopeDecodes() throws {
        let decoded = try scope()
        XCTAssertTrue(decoded.can_manage)
        XCTAssertEqual(decoded.locations.first?.displayName, "Downtown")
        XCTAssertEqual(decoded.locations.first?.timeZone?.identifier, "America/Los_Angeles")
        XCTAssertTrue(decoded.features.assistant)
        XCTAssertEqual(decoded.pending_requests, 3)
    }

    // MARK: Tabs

    func testTabsFollowTheAccount() throws {
        let crew = Session(userID: "u", role: "employee", displayName: "Sam", companyName: "Po",
                           employee: try employee(), manager: nil)
        XCTAssertEqual(AppTab.tabs(for: crew), [.schedule, .requests, .inbox, .me])

        let storeManager = Session(userID: "u", role: "employee", displayName: "Maria", companyName: "Po",
                                   employee: try employee(), manager: try scope())
        XCTAssertEqual(AppTab.tabs(for: storeManager), [.schedule, .requests, .manage, .inbox, .me])

        let admin = Session(userID: "u", role: "client", displayName: "Jordan", companyName: "Po",
                            employee: nil, manager: try scope(companyWide: true))
        XCTAssertEqual(AppTab.tabs(for: admin), [.manage, .inbox, .me])
        XCTAssertTrue(admin.isBusinessAdmin)
    }

    @MainActor
    func testRoutesLandOnATabTheAccountHas() throws {
        let state = AppState()
        state.phase = .ready(Session(userID: "u", role: "client", displayName: "Jordan", companyName: "Po",
                                     employee: nil, manager: try scope(companyWide: true)))
        state.selectedTab = .inbox
        // A business admin has no Schedule tab of their own.
        state.handleURL(URL(string: "matchaschedule://schedule")!)
        XCTAssertEqual(state.selectedTab, .manage)

        let id = "11111111-1111-1111-1111-111111111111"
        state.selectedTab = .me
        state.handlePush(["type": "schedule_request_pending", "metadata": ["request_id": id]])
        XCTAssertEqual(state.selectedTab, .manage)
        XCTAssertEqual(state.pendingApprovalID, id)
        XCTAssertEqual(state.notificationPrefix, "schedule_")
    }

    @MainActor
    func testCrewWithoutManageFallBackToRequests() throws {
        let state = AppState()
        state.phase = .ready(Session(userID: "u", role: "employee", displayName: "Sam", companyName: "Po",
                                     employee: try employee(), manager: nil))
        state.handleURL(URL(string: "matchaschedule://manage/requests/11111111-1111-1111-1111-111111111111")!)
        XCTAssertEqual(state.selectedTab, .requests)
        XCTAssertNil(state.pendingApprovalID)
        XCTAssertNil(state.notificationPrefix)
    }

    // MARK: Push routes

    func testManagerPushOpensApprovals() {
        let id = "11111111-1111-1111-1111-111111111111"
        XCTAssertEqual(PushRoute.destination(for: ["type": "schedule_request_pending", "metadata": ["request_id": id]]),
                       .manageApprovals(id))
        XCTAssertEqual(PushRoute.destination(for: ["type": "schedule_request_pending", "metadata": ["request_id": "../x"]]),
                       .manageApprovals(nil))
        // The requester's own updates still go to Requests.
        XCTAssertEqual(PushRoute.destination(for: ["type": "schedule_request_decided"]), .requests)
        XCTAssertEqual(PushRoute.destination(for: URL(string: "matchaschedule://manage/requests/\(id)")!),
                       .manageApprovals(id))
        XCTAssertEqual(PushRoute.destination(for: URL(string: "matchaschedule://manage")!), .manageApprovals(nil))
        XCTAssertEqual(PushRoute.destination(for: URL(string: "matchaschedule://manage/requests/nope")!),
                       .manageApprovals(nil))
    }

    // MARK: Requests and time off

    func testManagerRequestDecodesWithItsStoreAndProposal() throws {
        let json = """
        {"id":"r1","employee_id":"e1","employee_name":"Sam Ferreira","request_type":"availability",
         "status":"awaiting_manager","shift_id":null,"shift_starts_at":null,"shift_ends_at":null,
         "shift_role":null,"target_employee_id":null,"target_employee_name":"","counter_shift_id":null,
         "counter_shift_starts_at":null,"counter_shift_ends_at":null,"counter_shift_role":null,
         "unavailable_start":null,"unavailable_end":null,"availability_effective_on":"2026-10-19",
         "reason":"School","review_notes":null,"created_at":"2026-10-10T10:00:00Z","location_id":"loc-a",
         "proposed_availability":{"availability_state":"windows",
           "windows":[{"weekday":2,"start_time":"14:00","end_time":"20:00"},
                      {"weekday":1,"start_time":"09:00","end_time":"17:00"}]}}
        """
        let request = try JSONDecoder().decode(ScheduleRequest.self, from: Data(json.utf8))
        XCTAssertEqual(request.location_id, "loc-a")
        XCTAssertEqual(request.managerHeadline, "Sam Ferreira is changing availability")
        XCTAssertEqual(request.availabilityLines, ["Mon 9:00 AM – 5:00 PM", "Tue 2:00 PM – 8:00 PM"])

        // A proposal shape this build doesn't know must not break the list.
        let odd = json.replacingOccurrences(of: #""windows":[{"weekday":2"#, with: #""windows":"later","x":[{"weekday":2"#)
        XCTAssertEqual(try JSONDecoder().decode(ScheduleRequest.self, from: Data(odd.utf8)).availabilityLines, [])
    }

    func testSwapHeadlineNamesBothPeople() throws {
        let json = """
        {"id":"r2","employee_id":"e1","employee_name":"Kai","request_type":"swap","status":"awaiting_manager",
         "shift_id":"s1","shift_starts_at":"2026-10-12T09:00:00Z","shift_ends_at":"2026-10-12T17:00:00Z",
         "shift_role":"Barista","target_employee_id":"e2","target_employee_name":"Ruth","counter_shift_id":"s2",
         "counter_shift_starts_at":"2026-10-13T09:00:00Z","counter_shift_ends_at":"2026-10-13T17:00:00Z",
         "counter_shift_role":"Barista","unavailable_start":null,"unavailable_end":null,
         "availability_effective_on":null,"reason":null,"review_notes":null,"created_at":"2026-10-10T10:00:00Z"}
        """
        let request = try JSONDecoder().decode(ScheduleRequest.self, from: Data(json.utf8))
        XCTAssertEqual(request.managerHeadline, "Kai and Ruth want to swap")
        XCTAssertNil(request.location_id)
        XCTAssertNil(request.proposed_availability)
    }

    func testTimeOffDecodes() throws {
        let json = """
        [{"id":"p1","employee_id":"e1","employee_name":"Lena Abara","employee_email":"lena@example.com",
          "start_date":"2026-10-20","end_date":"2026-10-21","hours":16.0,"reason":"Family","request_type":"vacation",
          "status":"pending","approved_by":null,"approved_at":null,"denial_reason":null,
          "created_at":"2026-10-10T10:00:00Z"}]
        """
        let requests = try JSONDecoder().decode([PTOAdminRequest].self, from: Data(json.utf8))
        XCTAssertEqual(requests[0].hoursLine, "16 hours")
        XCTAssertEqual(requests[0].kindLabel, "Vacation")
        XCTAssertTrue(requests[0].datesLine.contains("–"))
    }

    // MARK: Conflicts

    private func detail(_ body: String) -> Data { Data(#"{"detail":\#(body)}"#.utf8) }

    func testForceableConflictsAreRecognised() throws {
        let meal = detail(#"{"code":"schedule_compliance","message":"May not comply","violations":[{"check":"meal_break","severity":"advisory","message":"Needs a 30-minute meal","statute":"Cal. Lab. Code § 512"}]}"#)
        let conflict = try XCTUnwrap(ScheduleConflict.parse(status: 409, data: meal))
        XCTAssertTrue(conflict.isMealBreak)
        XCTAssertTrue(conflict.prompt.contains("Needs a 30-minute meal [Cal. Lab. Code § 512]"))

        let overlap = detail(#"{"code":"schedule_conflict","message":"Already scheduled","conflicts":[{"starts_at":"2026-10-12T09:00:00Z","ends_at":"2026-10-12T17:00:00Z","role":"Barista"}]}"#)
        let double = try XCTUnwrap(ScheduleConflict.parse(status: 409, data: overlap))
        XCTAssertFalse(double.isMealBreak)
        XCTAssertTrue(double.prompt.contains("9:00 AM–5:00 PM (Barista)"), double.prompt)

        let fairWorkweek = detail(#"{"code":"schedule_compliance","violations":[{"check":"fair_workweek_notice","message":"Under 14 days notice"}]}"#)
        XCTAssertTrue(try XCTUnwrap(ScheduleConflict.parse(status: 409, data: fairWorkweek)).prompt
            .hasPrefix("This change may trigger Fair Workweek obligations"))

        // Not forceable: a stale edit, a request already decided, a hard block.
        XCTAssertNil(ScheduleConflict.parse(status: 409, data: detail(#"{"code":"shift_changed","message":"Reload"}"#)))
        XCTAssertNil(ScheduleConflict.parse(status: 409, data: detail(#"{"code":"request_not_manager_ready","status":"approved"}"#)))
        XCTAssertNil(ScheduleConflict.parse(status: 422, data: detail(#"{"code":"schedule_compliance","violations":[]}"#)))
        XCTAssertNil(ScheduleConflict.parse(status: 409, data: detail(#""Plain message""#)))
    }

    func testTheEditorSendsAMealBreakToTheShiftInsteadOfForcingIt() throws {
        let meal = try XCTUnwrap(ScheduleConflict.parse(status: 409, data: detail(
            #"{"code":"schedule_compliance","violations":[{"check":"meal_break","message":"Needs a meal"}]}"#
        )))
        XCTAssertFalse(ForcePrompt(conflict: meal, refusesMealBreak: true, retry: {}).forceable)
        XCTAssertTrue(ForcePrompt(conflict: meal, refusesMealBreak: false, retry: {}).forceable)
    }

    func testTheClientThrowsAForceableConflictAndKeepsOtherErrorsPlain() async throws {
        StubProtocol.register(status: 409, body: #"{"detail":{"code":"shift_full","message":"Shift already has 2 of 2"}}"#)
        defer { StubProtocol.unregister() }
        do {
            _ = try await APIClient.shared.requestData(method: "POST", path: "/employee-schedule/shifts/x/assignments")
            XCTFail("expected a conflict")
        } catch APIError.scheduleConflict(let conflict) {
            XCTAssertEqual(conflict.code, "shift_full")
            XCTAssertEqual(APIError.scheduleConflict(conflict).localizedDescription, "Shift already has 2 of 2")
        }

        StubProtocol.register(status: 409, body: #"{"detail":{"code":"shift_changed","message":"Reload the shift"}}"#)
        do {
            _ = try await APIClient.shared.requestData(method: "PUT", path: "/employee-schedule/shifts/x")
            XCTFail("expected an error")
        } catch APIError.httpError(let code, let message) {
            XCTAssertEqual(code, 409)
            XCTAssertEqual(message, "Reload the shift")
        }
    }

    func testFreshReadsSkipTheCache() async throws {
        StubProtocol.register(status: 200, body: #"{"requests":[]}"#)
        defer { StubProtocol.unregister() }
        _ = try await ManagerService.requests(location: "loc-a")
        let request = try XCTUnwrap(StubProtocol.last)
        XCTAssertEqual(request.cachePolicy, .reloadIgnoringLocalCacheData)
        XCTAssertTrue(request.url?.query?.contains("location=loc-a") == true)
        XCTAssertTrue(request.url?.query?.contains("status=awaiting_manager") == true)
    }
}

/// Answers every request with one canned response.
final class StubProtocol: URLProtocol {
    private static var status = 200
    private static var body = Data()
    static var last: URLRequest?

    static func register(status: Int, body: String) {
        self.status = status
        self.body = Data(body.utf8)
        last = nil
        URLProtocol.registerClass(StubProtocol.self)
    }

    static func unregister() { URLProtocol.unregisterClass(StubProtocol.self) }

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        Self.last = request
        let response = HTTPURLResponse(url: request.url!, statusCode: Self.status, httpVersion: nil,
                                       headerFields: ["Content-Type": "application/json"])!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Self.body)
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
}
