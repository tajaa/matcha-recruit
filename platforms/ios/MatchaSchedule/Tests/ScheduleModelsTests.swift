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
             "manager_note":"Front counter",
             "planned_breaks":[{"kind":"meal","ordinal":1,"start_local":"2026-09-23T12:00:00","duration_minutes":30,"source":"manager"}]}]},
          {"id":"two","location_id":"place","role":"Lead","department":null,
           "starts_at":"2026-09-24T09:00:00+00:00","ends_at":"2026-09-24T17:00:00+00:00",
           "break_minutes":null,"notes":null,"status":"published",
           "assignments":[{"employee_id":"peer","name":"Lin","status":"assigned"}],
           "has_conflict":true}
        ]}
        """
        let shifts = try JSONDecoder().decode(ShiftListResponse.self, from: Data(json.utf8)).shifts
        XCTAssertEqual(shifts.count, 2)
        // The real portal payload: no visibility flag (managers only), and a
        // local datetime for the break start.
        XCTAssertEqual(shifts[0].assignments[0].manager_note, "Front counter")
        XCTAssertEqual(shifts[0].assignments[0].planned_breaks?.first?.start_local, "2026-09-23T12:00:00")
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
        XCTAssertEqual(WallClock.format(day, "MMM d, yyyy"), "Sep 23, 2026")
    }

    func testMondayStoreWeekStartsOnMonday() {
        // Wednesday 2026-09-23
        let day = ISO8601DateFormatter().date(from: "2026-09-23T15:00:00Z")!
        XCTAssertEqual(WallClock.format(WallClock.weekStart(containing: day, weekStartWeekday: 1), "MMM d, yyyy"), "Sep 21, 2026")
        XCTAssertEqual(WallClock.format(WallClock.weekStart(containing: day, weekStartWeekday: 0), "MMM d, yyyy"), "Sep 20, 2026")
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
        XCTAssertEqual(ScheduleService.storeScoped(shifts, locationIDs: ["mine"]).map(\.id), ["here", "anywhere"])
        XCTAssertEqual(ScheduleService.storeScoped(shifts, locationIDs: []).count, 3)
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

    func testRealigningFromTheAnchorDayKeepsTheCurrentWeek() {
        // Wednesday 2026-09-23; the page opens on Sundays until the store's
        // week start (Monday) is learned.
        let wednesday = ISO8601DateFormatter().date(from: "2026-09-23T00:00:00Z")!
        let firstShown = WallClock.weekStart(containing: wednesday, weekStartWeekday: 0)
        // The old realign re-aligned the Sunday already on screen: last week.
        XCTAssertEqual(WallClock.format(WallClock.weekStart(containing: firstShown, weekStartWeekday: 1), "MMM d, yyyy"), "Sep 14, 2026")
        // Deriving from the anchor day lands on this week's Monday.
        XCTAssertEqual(WallClock.format(WallClock.weekStart(containing: wednesday, weekStartWeekday: 1), "MMM d, yyyy"), "Sep 21, 2026")
        // Navigation moves the anchor by whole weeks, so it stays aligned.
        let next = WallClock.move(wednesday, by: 1)
        XCTAssertEqual(WallClock.format(WallClock.weekStart(containing: next, weekStartWeekday: 1), "MMM d, yyyy"), "Sep 28, 2026")
    }

    func testLocationWithNoNameDecodesAndFallsBack() throws {
        let json = """
        {"locations":[
          {"id":"a","name":null,"address":null,"city":"Oakland","state":"CA","zipcode":null,"is_active":true,"week_start_weekday":1},
          {"id":"b","name":null,"city":null,"week_start_weekday":0},
          {"id":"c","name":"Mission","city":"San Francisco","week_start_weekday":0}
        ]}
        """
        let places = try JSONDecoder().decode(LocationsResponse.self, from: Data(json.utf8)).locations
        XCTAssertEqual(places.map(\.displayName), ["Oakland", "Your store", "Mission"])
    }

    func testPlannedBreakTimeIsTheStoresClockFace() {
        XCTAssertEqual(WallClock.clockTime("2026-09-23T12:00:00"), "12:00 PM")
        XCTAssertEqual(WallClock.clockTime("2026-09-23T06:30:00-07:00"), "6:30 AM")
        XCTAssertEqual(WallClock.clockTime("2026-09-23T00:05:00"), "12:05 AM")
        XCTAssertEqual(WallClock.clockTime("13:45"), "1:45 PM")
        XCTAssertEqual(WallClock.clockTime("soon"), "soon")
    }

    func testInstantsAreShownInTheDeviceZone() {
        let pacific = TimeZone(identifier: "America/Los_Angeles")!
        let locale = Locale(identifier: "en_US_POSIX")
        // Python's microseconds and both UTC spellings parse.
        XCTAssertNotNil(Instant.date("2026-09-23T17:00:00.123456+00:00"))
        XCTAssertNotNil(Instant.date("2026-09-23T17:00:00Z"))
        let label = Instant.label("2026-09-23T17:00:00.123456Z", timeZone: pacific, locale: locale)
        XCTAssertTrue(label.contains("10:00"), label)
        XCTAssertTrue(label.contains("Sep 23"), label)
        // An evening notice must not show tomorrow's date.
        XCTAssertTrue(Instant.label("2026-09-24T03:00:00Z", timeZone: pacific, locale: locale).contains("Sep 23"))
    }

    @MainActor
    func testPushTappedWhileSignedOutRoutesNobody() {
        let state = AppState()
        state.phase = .signedOut
        AppDelegate.pendingNotification = ["type": "schedule_published"]
        state.handlePush(["type": "schedule_published"])
        XCTAssertNil(AppDelegate.pendingNotification)
        XCTAssertEqual(state.selectedTab, 0)

        // While a session is still being restored it is kept for loadProfile.
        state.phase = .restoring
        AppDelegate.pendingNotification = ["type": "schedule_request_decided"]
        state.handlePush(["type": "schedule_request_decided"])
        XCTAssertNotNil(AppDelegate.pendingNotification)
        AppDelegate.pendingNotification = nil
    }

    func testAppearancePreferenceMapsToInterfaceStyle() {
        XCTAssertEqual(AppearancePreference.system.interfaceStyle, .unspecified)
        XCTAssertEqual(AppearancePreference.light.interfaceStyle, .light)
        XCTAssertEqual(AppearancePreference.dark.interfaceStyle, .dark)
        // Persisted by raw value; an unknown stored value falls back to nil
        // (so @AppStorage keeps its System default).
        XCTAssertEqual(AppearancePreference(rawValue: "dark"), .dark)
        XCTAssertNil(AppearancePreference(rawValue: "sepia"))
        XCTAssertEqual(AppearancePreference.allCases.map(\.label), ["System", "Light", "Dark"])
    }

    func testCountdownCountsCalendarDaysNotRoundedHours() {
        func at(_ iso: String) -> Date { ISO8601DateFormatter().date(from: iso)! }
        // Mon 8 PM → Wed 7 AM is two calendar days, though only 35 hours.
        XCTAssertEqual(WallClock.countdown(to: at("2026-09-30T07:00:00Z"), from: at("2026-09-28T20:00:00Z")), "in 2 days")
        // Mon 1 AM → Tue 11 PM is tomorrow, though 46 hours away.
        XCTAssertEqual(WallClock.countdown(to: at("2026-09-29T23:00:00Z"), from: at("2026-09-28T01:00:00Z")), "tomorrow")
        // Later today, and under 12 hours across midnight, read in hours.
        XCTAssertEqual(WallClock.countdown(to: at("2026-09-28T18:30:00Z"), from: at("2026-09-28T15:00:00Z")), "in 3h 30m")
        XCTAssertEqual(WallClock.countdown(to: at("2026-09-29T06:30:00Z"), from: at("2026-09-28T22:00:00Z")), "in 8h 30m")
        XCTAssertEqual(WallClock.countdown(to: at("2026-09-28T15:20:00Z"), from: at("2026-09-28T15:00:00Z")), "in 20m")
        XCTAssertEqual(WallClock.countdown(to: at("2026-09-28T15:00:00Z"), from: at("2026-09-28T15:00:30Z")), "starting now")
    }

    func testNowIsTheStoresClockFaceNotThePhones() {
        // 7 PM in New York is 4 PM at a Pacific store: a 5 PM shift has not started.
        let instant = ISO8601DateFormatter().date(from: "2026-09-28T23:00:00Z")!
        let store = WallClock.now(instant, timeZone: TimeZone(identifier: "America/Los_Angeles")!)
        let phone = WallClock.now(instant, timeZone: TimeZone(identifier: "America/New_York")!)
        XCTAssertEqual(WallClock.format(store, "HH:mm"), "16:00")
        XCTAssertEqual(WallClock.format(phone, "HH:mm"), "19:00")
        let json = #"{"locations":[{"id":"a","name":"Downtown","city":null,"week_start_weekday":0,"timezone":"America/Los_Angeles"}]}"#
        let place = try! JSONDecoder().decode(LocationsResponse.self, from: Data(json.utf8)).locations[0]
        XCTAssertEqual(place.timeZone?.identifier, "America/Los_Angeles")
    }

    func testNextShiftSkipsOneThatHasEnded() throws {
        let json = """
        {"shifts":[
          {"id":"done","location_id":null,"role":null,"department":null,"starts_at":"2026-09-28T06:30:00+00:00","ends_at":"2026-09-28T14:30:00+00:00","break_minutes":null,"notes":null,"status":"published","assignments":[]},
          {"id":"later","location_id":null,"role":null,"department":null,"starts_at":"2026-09-29T15:00:00+00:00","ends_at":"2026-09-29T23:00:00+00:00","break_minutes":null,"notes":null,"status":"published","assignments":[]}
        ]}
        """
        let shifts = try JSONDecoder().decode(ShiftListResponse.self, from: Data(json.utf8)).shifts
        func at(_ iso: String) -> Date { ISO8601DateFormatter().date(from: iso)! }
        // During the first shift it is the one shown ("On now")...
        XCTAssertEqual(ScheduleService.nextShift(in: shifts, now: at("2026-09-28T10:00:00Z"))?.id, "done")
        // ...and the minute it ends the card moves on.
        XCTAssertEqual(ScheduleService.nextShift(in: shifts, now: at("2026-09-28T14:30:00Z"))?.id, "later")
        XCTAssertNil(ScheduleService.nextShift(in: shifts, now: at("2026-09-30T00:00:00Z")))
    }

    func testFormattersAreBuiltOncePerPattern() {
        XCTAssertTrue(WallClock.formatter("h:mm a") === WallClock.formatter("h:mm a"))
        XCTAssertFalse(WallClock.formatter("h:mm a") === WallClock.formatter("EEE"))
    }

    func testWeekRangeUsesCalendarDays() {
        let day = ISO8601DateFormatter().date(from: "2026-09-23T15:00:00Z")!
        let week = WallClock.weekStart(containing: day)
        let (start, end) = WallClock.range(starting: week)
        XCTAssertEqual(start, "2026-09-20T00:00:00Z")
        XCTAssertEqual(end, "2026-09-27T00:00:00Z")
    }
}
