import XCTest
@testable import MatchaSchedule

final class ManagerWeekTests: XCTestCase {
    private func json(_ value: some Encodable) throws -> [String: Any] {
        let data = try JSONEncoder().encode(value)
        return try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
    }

    // MARK: Writing a shift time

    func testAWallClockRoundTripsUnchanged() throws {
        let day = try XCTUnwrap(WallClock.date("2026-10-12T00:00:00Z"))
        let nine = try XCTUnwrap(WallClock.date("2026-01-01T09:00:00Z"))
        let five = try XCTUnwrap(WallClock.date("2026-01-01T17:30:00Z"))
        let window = WallClock.window(day: day, start: nine, end: five)
        XCTAssertEqual(WallClock.iso(window.start), "2026-10-12T09:00:00Z")
        XCTAssertEqual(WallClock.iso(window.end), "2026-10-12T17:30:00Z")
        // What the server sends back reads the same.
        XCTAssertEqual(WallClock.iso(try XCTUnwrap(WallClock.date("2026-10-12T09:00:00+00:00"))), "2026-10-12T09:00:00Z")
    }

    func testAnEndBeforeTheStartFinishesTheNextDay() throws {
        let day = try XCTUnwrap(WallClock.date("2026-10-31T00:00:00Z"))
        let ten = try XCTUnwrap(WallClock.date("2026-01-01T22:00:00Z"))
        let six = try XCTUnwrap(WallClock.date("2026-01-01T06:00:00Z"))
        let window = WallClock.window(day: day, start: ten, end: six)
        XCTAssertEqual(WallClock.iso(window.start), "2026-10-31T22:00:00Z")
        XCTAssertEqual(WallClock.iso(window.end), "2026-11-01T06:00:00Z")
        // Equal times are a 24-hour shift, never a zero-length one.
        XCTAssertEqual(WallClock.iso(WallClock.window(day: day, start: ten, end: ten).end), "2026-11-01T22:00:00Z")
    }

    // MARK: Request bodies

    func testAPatchSendsOnlyWhatChanged() throws {
        var patch = ShiftPatch()
        patch.required_staff = 3
        XCTAssertEqual(try json(patch) as NSDictionary, ["required_staff": 3])

        patch = ShiftPatch()
        patch.notes = .some(nil)
        let cleared = try json(patch)
        XCTAssertEqual(cleared.count, 1)
        XCTAssertTrue(cleared["notes"] is NSNull, "clearing a note must send an explicit null")

        XCTAssertEqual(try json(ShiftPatch(status: "cancelled")) as NSDictionary, ["status": "cancelled"])
        XCTAssertEqual(try json(ShiftPatch(break_mode: "auto")) as NSDictionary, ["break_mode": "auto"])
    }

    func testANewShiftAsksForTheLegalBreak() throws {
        let body = ShiftCreateBody(job_id: "j", starts_at: "a", ends_at: "b", location_id: "l", required_staff: 2, notes: nil)
        let encoded = try json(body)
        XCTAssertEqual(encoded["break_mode"] as? String, "auto")
        XCTAssertEqual(encoded["required_staff"] as? Int, 2)
        XCTAssertNil(encoded["notes"])
    }

    // MARK: Reading the week

    func testTheWeekDecodesWithOpenSeats() throws {
        let response = """
        {"week_start":"2026-10-12","location_id":"loc-a",
         "shifts":[
          {"id":"s1","location_id":"loc-a","template_id":null,"series_id":null,"role":"Barista","department":null,
           "starts_at":"2026-10-12T06:30:00+00:00","ends_at":"2026-10-12T14:30:00+00:00","break_minutes":30,
           "required_staff":3,"color":null,"notes":null,"status":"draft","kind":"work","training_requirement_id":null,
           "job_id":"job-1","published_at":null,
           "assignments":[{"employee_id":"e1","name":"Sam Ferreira","job_title":"Barista","status":"assigned"}]},
          {"id":"s2","location_id":null,"role":"Shift Lead","department":null,
           "starts_at":"2026-10-13T08:00:00+00:00","ends_at":"2026-10-13T16:00:00+00:00","break_minutes":30,
           "required_staff":1,"color":null,"notes":"Opening","status":"cancelled","kind":"work","job_id":"job-2",
           "published_at":"2026-10-01T10:00:00+00:00","assignments":[]}],
         "roster":[{"id":"e1","name":"Sam Ferreira","job_title":"Barista","department":null,
                    "job_ids":["job-1"],"job_qualifications":[]}],
         "roster_flags":null,
         "summary":{"total_shifts":2,"published":0,"draft":1,"open_shifts":1,"assigned":1}}
        """
        let week = try JSONDecoder().decode(ManagerWeek.self, from: Data(response.utf8))
        XCTAssertEqual(week.shifts[0].openSeats, 2)
        XCTAssertEqual(week.shifts[0].job_id, "job-1")
        // Nothing to fill on a cancelled shift.
        XCTAssertEqual(week.shifts[1].openSeats, 0)
        XCTAssertNil(week.shifts[1].location_id)
        XCTAssertEqual(week.roster[0].job_ids, ["job-1"])
        XCTAssertEqual(week.summary.draft, 1)
    }

    func testCrewFeedsStillDecodeWithoutManagerFields() throws {
        let shift = """
        {"id":"s1","location_id":"loc-a","role":"Barista","department":null,"starts_at":"2026-10-12T06:30:00Z",
         "ends_at":"2026-10-12T14:30:00Z","break_minutes":30,"notes":null,"status":"published","assignments":[]}
        """
        let decoded = try JSONDecoder().decode(ScheduleShift.self, from: Data(shift.utf8))
        XCTAssertNil(decoded.required_staff)
        XCTAssertEqual(decoded.openSeats, 0)
    }

    func testAnEmptyQualifiedListMeansAnyoneQualifies() throws {
        let jobs = try JSONDecoder().decode(JobsResponse.self, from: Data("""
        {"jobs":[{"id":"j1","name":"Barista","location_id":"loc-a","color":null,"notes":null,"employee_ids":[],
                  "credential_grace_days":null,"credential_requirements":[]},
                 {"id":"j2","name":"Shift Lead","location_id":null,"color":null,"notes":null,"employee_ids":["e2"],
                  "credential_grace_days":null,"credential_requirements":[]}]}
        """.utf8)).jobs
        XCTAssertTrue(jobs[0].qualifies("anyone"))
        XCTAssertTrue(jobs[1].qualifies("e2"))
        XCTAssertFalse(jobs[1].qualifies("e1"))
    }

    func testPlanningInputsAreGuidanceThatNeverFails() throws {
        let response = """
        {"roster":[{"employee_id":"e1","name":"Sam","jobs":["Barista"],"availability_state":"windows",
                    "windows":{"1":[["09:00","17:00"]]},
                    "time_away":[{"start":"2026-10-14","end":"2026-10-15"}],
                    "caps":{},"load":{"minutes":1110,"shifts":3,"days":["2026-10-12"]}},
                   {"employee_id":"e2","name":"Kai","time_away":"unexpected","load":{"minutes":480,"shifts":1}}],
         "open_slots":[],"policy":{}}
        """
        let inputs = try JSONDecoder().decode(PlanningInputs.self, from: Data(response.utf8))
        XCTAssertEqual(inputs.roster.count, 2)
        XCTAssertEqual(inputs.roster[0].loadLine, "18.5h · 3 shifts")
        XCTAssertTrue(inputs.roster[0].isAway(on: "2026-10-15"))
        XCTAssertFalse(inputs.roster[0].isAway(on: "2026-10-16"))
        XCTAssertEqual(inputs.roster[1].loadLine, "8h · 1 shift")
        XCTAssertTrue(inputs.roster[1].time_away.isEmpty)

        let broken = try JSONDecoder().decode(PlanningInputs.self, from: Data(#"{"roster":"nope"}"#.utf8))
        XCTAssertTrue(broken.roster.isEmpty)
    }
}
