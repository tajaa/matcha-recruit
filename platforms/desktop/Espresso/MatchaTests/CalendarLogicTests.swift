import XCTest
@testable import Matcha

/// The Calendar tab's and the email sheet's rules, with a fake backend and a
/// pinned Los Angeles calendar (2026-03-08 springs forward, 2026-11-01 falls
/// back). Nothing here touches the network or the signed-in session.
@MainActor
final class CalendarLogicTests: XCTestCase {

    private var la: Calendar = {
        var c = Calendar(identifier: .gregorian)
        c.timeZone = TimeZone(identifier: "America/Los_Angeles")!
        c.firstWeekday = 1
        return c
    }()

    private func date(_ y: Int, _ m: Int, _ d: Int, _ h: Int = 0, _ min: Int = 0) -> Date {
        la.date(from: DateComponents(year: y, month: m, day: d, hour: h, minute: min))!
    }

    private func event(_ id: String, _ title: String, start: String, end: String, allDay: Bool = false)
        -> MWCalendarEvent {
        MWCalendarEvent(id: id, title: title, notes: "Old notes", location: "Old place", allDay: allDay,
                        start: start, end: end, sourceKind: "manual", sourceRef: nil, sourceLabel: nil)
    }

    private func clock(_ date: Date) -> Int {
        let c = la.dateComponents([.hour, .minute], from: date)
        return (c.hour ?? 0) * 60 + (c.minute ?? 0)
    }

    // MARK: - Email batch (review #1)

    func testABatchStopsOnceTheAccountThatStartedItIsGone() async {
        let backend = FakeCalendarBackend()
        var signedIn = true
        backend.onCreate = { signedIn = false }  // someone else signs in after the first add
        let drafts = (0..<3).map { CalendarDraft(on: date(2026, 10, 20 + $0), hour: 9, title: "E\($0)", calendar: la) }
        let outcome = await EmailCalendarRules.add(
            drafts, emailId: "m1", subject: "Plans", backend: backend, calendar: la, stillOwner: { signedIn })
        XCTAssertEqual(backend.created.map(\.title), ["E0"])
        XCTAssertTrue(outcome.stopped)
        XCTAssertEqual(outcome.added, [drafts[0].id])
    }

    func testABatchStopsWhenItsTaskIsCancelled() async {
        let backend = FakeCalendarBackend()
        let drafts = [CalendarDraft(on: date(2026, 10, 20), hour: 9, title: "E", calendar: la)]
        let task = Task { @MainActor in
            await EmailCalendarRules.add(drafts, emailId: "m1", subject: "", backend: backend,
                                         calendar: la, stillOwner: { true })
        }
        task.cancel()
        let outcome = await task.value
        XCTAssertTrue(outcome.stopped)
        XCTAssertTrue(backend.created.isEmpty)
    }

    // MARK: - Clock axis (review #2, #11)

    func testANewEventsHourIsTheClockReadingOnBothDSTDays() {
        for day in [date(2026, 3, 8), date(2026, 11, 1)] {
            let draft = CalendarDraft(on: day, hour: 9, calendar: la)
            XCTAssertEqual(clock(draft.start), 9 * 60, "\(day)")
            XCTAssertEqual(draft.end.timeIntervalSince(draft.start), 3600)
        }
    }

    func testA9AMEventSitsOnThe9AMLineOnDSTDays() {
        for (day, start, end) in [(date(2026, 3, 8), "2026-03-08T09:00:00-07:00", "2026-03-08T10:00:00-07:00"),
                                  (date(2026, 11, 1), "2026-11-01T09:00:00-08:00", "2026-11-01T10:00:00-08:00")] {
            let entry = CalendarEntry(event: event("e", "Standup", start: start, end: end), calendar: la)!
            let placed = WeekLayout.place([entry], on: day, hourHeight: 46, calendar: la)
            XCTAssertEqual(placed.first?.top ?? -1, 9 * 46, accuracy: 0.01, "\(day)")
        }
    }

    func testBlocksDrawnTallerThanTheirTimeDoNotOverlap() {
        let a = CalendarEntry(event: event("a", "A", start: "2026-10-20T09:00:00-07:00",
                                           end: "2026-10-20T09:15:00-07:00"), calendar: la)!
        let b = CalendarEntry(event: event("b", "B", start: "2026-10-20T09:15:00-07:00",
                                           end: "2026-10-20T09:30:00-07:00"), calendar: la)!
        let placed = WeekLayout.place([a, b], on: date(2026, 10, 20), hourHeight: 46, calendar: la)
        let columns = Dictionary(uniqueKeysWithValues: placed.map { ($0.entry.id, $0.column) })
        XCTAssertNotEqual(columns["e:a"], columns["e:b"])
        XCTAssertTrue(placed.allSatisfy { $0.columns == 2 })
    }

    // MARK: - All-day length (review #3)

    func testMovingAnAllDayStartKeepsItsCalendarDays() {
        // March 7-9 crosses the spring change: 47 elapsed hours, three days.
        let trip = CalendarDraft(title: "Trip", allDay: true, start: date(2026, 3, 7), end: date(2026, 3, 9))
        let moved = trip.movingStart(to: date(2026, 3, 20, 10), calendar: la)
        let fields = moved.fields(calendar: la)
        XCTAssertEqual(fields.start, "2026-03-20")
        XCTAssertEqual(fields.end, "2026-03-22")
        let timed = CalendarDraft(on: date(2026, 10, 20), hour: 9, calendar: la)
            .movingStart(to: date(2026, 10, 21, 14), calendar: la)
        XCTAssertEqual(timed.end.timeIntervalSince(timed.start), 3600)
    }

    // MARK: - Range loading (review #4, #5, #6)

    func testFocusLoadsWhenTheGridChangesEvenIfTheOldGridHeldTheDay() async {
        let backend = FakeCalendarBackend()
        let vm = CalendarViewModel(backend: backend, calendar: la, now: date(2026, 10, 15))
        await vm.load()
        XCTAssertEqual(backend.feedRequests.last?.0, date(2026, 9, 27))
        // October's grid runs to November 7, but November's grid is another range.
        XCTAssertTrue(vm.focus(date(2026, 11, 1), load: false))
        await vm.load()
        XCTAssertEqual(backend.feedRequests.last?.0, date(2026, 11, 1))
        XCTAssertFalse(vm.focus(date(2026, 11, 20), load: false))
    }

    func testSavingAnEventOutsideTheGridShowsItsDay() async throws {
        let backend = FakeCalendarBackend()
        let vm = CalendarViewModel(backend: backend, calendar: la, now: date(2026, 10, 15))
        await vm.load()
        try await vm.save(CalendarDraft(on: date(2026, 12, 1), hour: 10, title: "Party", calendar: la), editing: nil)
        XCTAssertEqual(backend.created.map(\.title), ["Party"])
        XCTAssertEqual(vm.selectedDay, date(2026, 12, 1))
        XCTAssertTrue(vm.visibleRange?.contains(date(2026, 12, 1)) ?? false)
        XCTAssertEqual(backend.feedRequests.last?.0, date(2026, 11, 29))
    }

    func testAYearLongGoogleEventShowsOnEveryVisibleDay() async {
        let backend = FakeCalendarBackend()
        backend.google = [MWGoogleCalendarEvent(id: "g1", title: "Sabbatical", start: "2026-01-01",
                                                end: "2026-12-31", allDay: true, location: nil, link: nil,
                                                attendeeCount: nil)]
        let vm = CalendarViewModel(backend: backend, calendar: la, now: date(2026, 10, 15))
        await vm.load()
        for day in [date(2026, 9, 27), date(2026, 10, 15), date(2026, 11, 7)] {
            XCTAssertEqual(vm.entries(on: day).map(\.title), ["Sabbatical"], "\(day)")
        }
        XCTAssertTrue(vm.entries(on: date(2026, 11, 8)).isEmpty)
    }

    // MARK: - Drag (review #7)

    func testDraggingSendsOnlyTheNewTimes() async {
        let backend = FakeCalendarBackend()
        let vm = CalendarViewModel(backend: backend, calendar: la, now: date(2026, 10, 15))
        await vm.move(event("e1", "Dentist", start: "2026-10-15T15:00:00-07:00", end: "2026-10-15T16:00:00-07:00"),
                      to: date(2026, 10, 17))
        XCTAssertEqual(backend.moved.count, 1)
        XCTAssertEqual(backend.moved.first?.id, "e1")
        XCTAssertEqual(backend.moved.first?.start, "2026-10-17T15:00:00-07:00")
        XCTAssertEqual(backend.moved.first?.end, "2026-10-17T16:00:00-07:00")
        XCTAssertTrue(backend.updated.isEmpty, "a drag must not write the cached title, notes or place")
    }

    // MARK: - Timezone report (review #8)

    func testTheTimezoneReportIsPerSessionAndIgnoresAStaleOne() {
        var cache = TimeZoneReportCache()
        XCTAssertTrue(cache.needsReport("America/Los_Angeles"))
        cache.recordReport("America/Los_Angeles", startedIn: cache.session)
        XCTAssertFalse(cache.needsReport("America/Los_Angeles"))
        let first = cache.session
        cache.reset()  // sign-out
        XCTAssertTrue(cache.needsReport("America/Los_Angeles"))
        cache.recordReport("America/Los_Angeles", startedIn: first)  // the old account's report lands late
        XCTAssertTrue(cache.needsReport("America/Los_Angeles"))
    }

    // MARK: - Email sheet (review #9, #10)

    func testProposalsTheEmailAlreadyAddedStartUnticked() {
        let existing = [event("x", "Dinner at Nopa", start: "2026-10-16T19:00:00-07:00", end: "2026-10-16T21:00:00-07:00")]
        let drafts = [
            CalendarDraft(title: "Dinner", allDay: false, start: date(2026, 10, 16, 19), end: date(2026, 10, 16, 21)),
            CalendarDraft(title: "dinner at nopa ", allDay: false, start: date(2026, 10, 16, 20), end: date(2026, 10, 16, 21)),
            CalendarDraft(title: "Brunch", allDay: false, start: date(2026, 10, 18, 11), end: date(2026, 10, 18, 12)),
        ]
        let marked = EmailCalendarRules.markRepeats(drafts, existing: existing, calendar: la)
        XCTAssertEqual(marked.map(\.include), [false, false, true])
        XCTAssertEqual(marked.map(\.alreadyOnCalendar), [true, true, false])
    }

    func testAddNeedsAFinishedScan() {
        let drafts = [CalendarDraft(on: date(2026, 10, 20), hour: 9, title: "E", calendar: la)]
        XCTAssertTrue(EmailCalendarRules.canAdd(ready: true, saving: false, drafts: drafts))
        XCTAssertFalse(EmailCalendarRules.canAdd(ready: false, saving: false, drafts: drafts))
        XCTAssertFalse(EmailCalendarRules.canAdd(ready: true, saving: true, drafts: drafts))
        var unticked = drafts
        unticked[0].include = false
        XCTAssertFalse(EmailCalendarRules.canAdd(ready: true, saving: false, drafts: unticked))
    }
}

/// Records what the Calendar asked the server for.
@MainActor
private final class FakeCalendarBackend: CalendarBackend {
    var feedRequests: [(Date, Date)] = []
    var google: [MWGoogleCalendarEvent] = []
    var created: [CalendarService.EventFields] = []
    var updated: [(id: String, fields: CalendarService.EventFields)] = []
    var moved: [(id: String, start: String, end: String)] = []
    var deleted: [String] = []
    var onCreate: (() -> Void)?

    func feed(from start: Date, to end: Date) async throws -> MWCalendarFeed {
        feedRequests.append((start, end))
        return MWCalendarFeed(timezone: "America/Los_Angeles", events: [], todos: [],
                              google: MWGoogleCalendarFeed(status: "ok", events: google))
    }

    func createEvent(_ fields: CalendarService.EventFields, sourceKind: String,
                     sourceRef: String?, sourceLabel: String?) async throws -> MWCalendarEvent {
        created.append(fields)
        onCreate?()
        return made(fields.title, fields.start, fields.end ?? fields.start)
    }

    func updateEvent(id: String, _ fields: CalendarService.EventFields) async throws -> MWCalendarEvent {
        updated.append((id, fields))
        return made(fields.title, fields.start, fields.end ?? fields.start)
    }

    func moveEvent(id: String, start: String, end: String) async throws -> MWCalendarEvent {
        moved.append((id, start, end))
        return made("moved", start, end)
    }

    func deleteEvent(id: String) async throws { deleted.append(id) }

    func reportTimeZoneIfNeeded() async {}

    private func made(_ title: String, _ start: String, _ end: String) -> MWCalendarEvent {
        MWCalendarEvent(id: UUID().uuidString, title: title, notes: nil, location: nil, allDay: start.count == 10,
                        start: start, end: end, sourceKind: "manual", sourceRef: nil, sourceLabel: nil)
    }
}
