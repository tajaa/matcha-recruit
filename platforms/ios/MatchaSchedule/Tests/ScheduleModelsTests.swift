import XCTest
@testable import MatchaSchedule

final class ScheduleModelsTests: XCTestCase {
    @MainActor
    func testRefreshRequestsCoalesce() async throws {
        let gate = RefreshGate()
        var calls = 0
        let response = TokenResponse(access_token: "access", refresh_token: "refresh",
                                     user: AuthUser(id: "id", email: "a@example.com", role: "employee"))
        let first = Task { try await gate.run {
            calls += 1
            try await Task.sleep(nanoseconds: 100_000_000)
            return response
        } }
        try await Task.sleep(nanoseconds: 20_000_000)
        let second = Task { try await gate.run {
            calls += 1
            return response
        } }
        let one = try await first.value
        let two = try await second.value
        XCTAssertEqual(one.access_token, two.access_token)
        XCTAssertEqual(calls, 1)
    }

    func testEmployeeAndTeamShiftShapes() throws {
        let json = """
        {"shifts":[
          {"id":"one","location_id":"place","role":"Barista","department":null,
           "starts_at":"2026-09-23T09:00:00+00:00","ends_at":"2026-09-23T17:00:00+00:00",
           "break_minutes":30,"notes":null,"status":"published",
           "assignments":[{"employee_id":"me","name":"Ada","status":"assigned",
             "manager_note":"Front counter","manager_note_visible_to_employee":true,
             "planned_breaks":[{"kind":"meal","ordinal":1,"start_local":"12:00","duration_minutes":30,"source":"manager"}]}]},
          {"id":"two","location_id":"place","role":"Lead","department":null,
           "starts_at":"2026-09-24T09:00:00+00:00","ends_at":"2026-09-24T17:00:00+00:00",
           "break_minutes":null,"notes":null,"status":"published",
           "assignments":[{"employee_id":"peer","name":"Lin","status":"assigned"}],
           "has_conflict":true}
        ]}
        """
        let shifts = try JSONDecoder().decode(ShiftListResponse.self, from: Data(json.utf8)).shifts
        XCTAssertEqual(shifts.count, 2)
        XCTAssertEqual(shifts[0].assignments[0].planned_breaks?.first?.start_local, "12:00")
        XCTAssertNil(shifts[1].assignments[0].manager_note)
        XCTAssertEqual(shifts[1].has_conflict, true)
    }

    func testWallClockDoesNotShiftWithDeviceTimeZone() {
        XCTAssertEqual(WallClock.label("2026-09-23T09:30:00+00:00", format: "h:mm a"), "9:30 AM")
    }

    func testLocalTodayMapsToUTCMidnight() {
        let now = ISO8601DateFormatter().date(from: "2026-09-24T02:00:00Z")!
        let losAngeles = TimeZone(identifier: "America/Los_Angeles")!
        let day = WallClock.today(now: now, timeZone: losAngeles)
        XCTAssertEqual(WallClock.weekLabel(day), "Sep 23, 2026")
    }

    func testMondayStoreWeekStartsOnMonday() {
        // Wednesday 2026-09-23
        let day = ISO8601DateFormatter().date(from: "2026-09-23T15:00:00Z")!
        XCTAssertEqual(WallClock.weekLabel(WallClock.weekStart(containing: day, weekStartWeekday: 1)), "Sep 21, 2026")
        XCTAssertEqual(WallClock.weekLabel(WallClock.weekStart(containing: day, weekStartWeekday: 0)), "Sep 20, 2026")
        let json = """
        {"locations":[{"id":"a","name":"Mission","week_start_weekday":1}]}
        """
        let places = try! JSONDecoder().decode(LocationsResponse.self, from: Data(json.utf8))
        XCTAssertEqual(places.locations[0].week_start_weekday, 1)
    }

    func testTeamTabIsScopedToTheEmployeesStore() throws {
        let json = """
        {"shifts":[
          {"id":"here","location_id":"mine","role":null,"department":null,"starts_at":"2026-09-23T09:00:00+00:00","ends_at":"2026-09-23T17:00:00+00:00","break_minutes":null,"notes":null,"status":"published","assignments":[]},
          {"id":"elsewhere","location_id":"other","role":null,"department":null,"starts_at":"2026-09-23T09:00:00+00:00","ends_at":"2026-09-23T17:00:00+00:00","break_minutes":null,"notes":null,"status":"published","assignments":[]},
          {"id":"anywhere","location_id":null,"role":null,"department":null,"starts_at":"2026-09-23T09:00:00+00:00","ends_at":"2026-09-23T17:00:00+00:00","break_minutes":null,"notes":null,"status":"published","assignments":[]}
        ]}
        """
        let shifts = try JSONDecoder().decode(ShiftListResponse.self, from: Data(json.utf8)).shifts
        XCTAssertEqual(ScheduleService.teamShifts(shifts, locationIDs: ["mine"]).map(\.id), ["here", "anywhere"])
        XCTAssertEqual(ScheduleService.teamShifts(shifts, locationIDs: []).count, 3)
    }

    func testServerErrorMessagesAreUnwrapped() {
        let client = APIClient.shared
        XCTAssertEqual(client.extractErrorMessage(from: Data(#"{"detail":"Invalid email or password"}"#.utf8)),
                       "Invalid email or password")
        XCTAssertEqual(client.extractErrorMessage(from: Data(#"{"detail":{"code":"same_day_assignment","message":"Employee already has a shift on this day"}}"#.utf8)),
                       "Employee already has a shift on this day")
        XCTAssertEqual(client.extractErrorMessage(from: Data(#"{"detail":[{"loc":["body","unavailable_end"],"msg":"field required","type":"missing"}]}"#.utf8)),
                       "unavailable_end: field required")
    }

    func testWrongPasswordIsNotASessionExpiry() {
        let error = SessionError.invalidCredentials("Invalid email or password")
        XCTAssertEqual(error.errorDescription, "Invalid email or password")
        XCTAssertFalse(AuthService.isNetworkFailure(error))
        XCTAssertTrue(AuthService.isNetworkFailure(APIError.networkUnavailable(URLError(.notConnectedToInternet))))
    }

    @MainActor
    func testFirstLaunchPurgesLeftoverKeychainSession() {
        let defaults = UserDefaults(suiteName: "test.\(UUID().uuidString)")!
        XCTAssertTrue(AppState.purgeKeychainOnFirstLaunch(defaults: defaults))
        XCTAssertFalse(AppState.purgeKeychainOnFirstLaunch(defaults: defaults))
    }

    func testWeekRangeUsesCalendarDays() {
        let day = ISO8601DateFormatter().date(from: "2026-09-23T15:00:00Z")!
        let week = WallClock.weekStart(containing: day)
        let (start, end) = WallClock.range(starting: week)
        XCTAssertEqual(start, "2026-09-20T00:00:00Z")
        XCTAssertEqual(end, "2026-09-27T00:00:00Z")
    }
}
