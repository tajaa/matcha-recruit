import Foundation

/// One thing on the calendar view, whatever it came from.
struct CalendarEntry: Identifiable, Hashable {
    enum Kind: Hashable {
        case espresso(MWCalendarEvent)
        case google(MWGoogleCalendarEvent)
        case apple(AppleCalendarEvent)
        case todo(MWCalendarTodo)
    }

    let id: String
    let kind: Kind
    let title: String
    /// Timed: the start instant. All day: the first day's local midnight.
    let start: Date
    /// Timed: the end instant. All day: the LAST day's local midnight.
    let end: Date
    let allDay: Bool

    var isTodo: Bool { if case .todo = kind { return true } else { return false } }
    var isDone: Bool { if case .todo(let t) = kind { return t.isDone } else { return false } }
    var espressoEvent: MWCalendarEvent? { if case .espresso(let e) = kind { return e } else { return nil } }
    var location: String? {
        switch kind {
        case .espresso(let e): return e.location
        case .google(let g): return g.location
        case .apple(let a): return a.location
        case .todo: return nil
        }
    }

    init?(event: MWCalendarEvent, calendar: Calendar = .current) {
        guard let s = CalendarWire.date(event.start, calendar: calendar),
              let e = CalendarWire.date(event.end, calendar: calendar) else { return nil }
        self.init(id: "e:\(event.id)", kind: .espresso(event), title: event.title,
                  start: s, end: max(s, e), allDay: event.allDay)
    }

    init?(google: MWGoogleCalendarEvent, calendar: Calendar = .current) {
        guard let s = CalendarWire.date(google.start, calendar: calendar) else { return nil }
        let e = google.end.flatMap { CalendarWire.date($0, calendar: calendar) } ?? s
        self.init(id: "g:\(google.id)", kind: .google(google), title: google.title,
                  start: s, end: max(s, e), allDay: google.allDay)
    }

    init?(apple: AppleCalendarEvent, calendar: Calendar = .current) {
        guard let s = CalendarWire.date(apple.start, calendar: calendar),
              let e = CalendarWire.date(apple.end, calendar: calendar) else { return nil }
        self.init(id: "a:\(apple.id)", kind: .apple(apple), title: apple.title,
                  start: s, end: max(s, e), allDay: apple.all_day)
    }

    init?(todo: MWCalendarTodo, calendar: Calendar = .current) {
        guard let d = CalendarWire.day(todo.dueDate, calendar: calendar) else { return nil }
        self.init(id: "t:\(todo.id)", kind: .todo(todo), title: todo.title, start: d, end: d, allDay: true)
    }

    private init(id: String, kind: Kind, title: String, start: Date, end: Date, allDay: Bool) {
        self.id = id
        self.kind = kind
        self.title = title
        self.start = start
        self.end = end
        self.allDay = allDay
    }

    /// The local days this entry shows on, kept to `lower...upper` when given
    /// (a timed event ending exactly at midnight does not spill into the next
    /// day). Clipping comes before the bound: a Google event can start months
    /// before the range it was listed for and still cover all of it.
    func days(in calendar: Calendar, within lower: Date? = nil, through upper: Date? = nil,
              limit: Int = 62) -> [Date] {
        var first = calendar.startOfDay(for: start)
        var lastInstant = end
        if !allDay, end > start, calendar.startOfDay(for: end) == end { lastInstant = end.addingTimeInterval(-1) }
        var last = calendar.startOfDay(for: lastInstant)
        if let lower { first = max(first, calendar.startOfDay(for: lower)) }
        if let upper { last = min(last, calendar.startOfDay(for: upper)) }
        var out: [Date] = []
        var day = first
        while day <= last, out.count < limit {
            out.append(day)
            guard let next = calendar.date(byAdding: .day, value: 1, to: day) else { break }
            day = next
        }
        return out
    }
}

/// What the Calendar needs from the server: `CalendarService` in the app, a
/// fake in tests.
@MainActor
protocol CalendarBackend {
    func feed(from start: Date, to end: Date) async throws -> MWCalendarFeed
    func createEvent(_ fields: CalendarService.EventFields, sourceKind: String,
                     sourceRef: String?, sourceLabel: String?) async throws -> MWCalendarEvent
    func updateEvent(id: String, _ fields: CalendarService.EventFields) async throws -> MWCalendarEvent
    /// Only the times: the server merges them into the event as it is now.
    func moveEvent(id: String, start: String, end: String) async throws -> MWCalendarEvent
    func deleteEvent(id: String) async throws
    func reportTimeZoneIfNeeded() async
}

extension CalendarService: CalendarBackend {}

/// The Calendar tab: what range is shown, what is in it, and the edits.
@MainActor
@Observable
final class CalendarViewModel {
    enum Mode: String, CaseIterable, Identifiable {
        case month = "Month", week = "Week"
        var id: String { rawValue }
    }

    var mode: Mode = .month
    /// Any day inside the month or week on screen.
    private(set) var anchor: Date
    var selectedDay: Date

    private(set) var entries: [CalendarEntry] = []
    private(set) var byDay: [Date: [CalendarEntry]] = [:]
    /// ok | partial | not_connected | needs_permission | error | skipped
    private(set) var googleFeed = MWGoogleCalendarFeed(status: "skipped", events: [])
    var googleStatus: String { googleFeed.status }
    private(set) var appleStatus = "not_connected"
    private(set) var isLoading = false
    private(set) var hasLoaded = false
    /// The days the last successful load covered. Changes only when a
    /// different range arrives, not on a reload after an edit.
    private(set) var loadedRange: ClosedRange<Date>?
    var errorMessage: String?

    @ObservationIgnored private var loadGeneration = 0
    @ObservationIgnored private let backend: CalendarBackend
    let calendar: Calendar

    /// `backend` defaults to `CalendarService.shared`.
    init(backend: CalendarBackend? = nil, calendar: Calendar = .current, now: Date = Date()) {
        self.backend = backend ?? CalendarService.shared
        self.calendar = calendar
        anchor = calendar.startOfDay(for: now)
        selectedDay = calendar.startOfDay(for: now)
    }

    // MARK: Range

    var visibleDays: [Date] {
        switch mode {
        case .month:
            let comps = calendar.dateComponents([.year, .month], from: anchor)
            guard let first = calendar.date(from: comps) else { return [] }
            let offset = (calendar.component(.weekday, from: first) - calendar.firstWeekday + 7) % 7
            guard let start = calendar.date(byAdding: .day, value: -offset, to: first) else { return [] }
            return (0..<42).compactMap { calendar.date(byAdding: .day, value: $0, to: start) }
        case .week:
            guard let start = calendar.dateInterval(of: .weekOfYear, for: anchor)?.start else { return [] }
            return (0..<7).compactMap { calendar.date(byAdding: .day, value: $0, to: start) }
        }
    }

    var title: String {
        switch mode {
        case .month:
            return anchor.formatted(.dateTime.month(.wide).year())
        case .week:
            let days = visibleDays
            guard let first = days.first, let last = days.last else { return "" }
            let sameMonth = calendar.isDate(first, equalTo: last, toGranularity: .month)
            let start = first.formatted(.dateTime.month(.abbreviated).day())
            let end = sameMonth ? last.formatted(.dateTime.day()) : last.formatted(.dateTime.month(.abbreviated).day())
            return "\(start) – \(end), \(last.formatted(.dateTime.year()))"
        }
    }

    var visibleRange: ClosedRange<Date>? {
        let days = visibleDays
        guard let first = days.first, let last = days.last else { return nil }
        return first...last
    }

    /// The range on screen is not the one last loaded.
    var needsLoad: Bool { !hasLoaded || visibleRange != loadedRange }

    func isInAnchorMonth(_ day: Date) -> Bool {
        calendar.isDate(day, equalTo: anchor, toGranularity: .month)
    }

    func shift(_ delta: Int) {
        let unit: Calendar.Component = mode == .month ? .month : .weekOfYear
        guard let next = calendar.date(byAdding: unit, value: delta, to: anchor) else { return }
        anchor = next
        if mode == .week || !calendar.isDate(selectedDay, equalTo: next, toGranularity: .month) {
            selectedDay = calendar.startOfDay(for: mode == .week ? (visibleDays.first ?? next) : firstOfMonth(next))
        }
        Task { await load() }
    }

    /// The person switched Month / Week.
    func setMode(_ next: Mode) {
        guard next != mode else { return }
        mode = next
        if mode == .week { anchor = selectedDay }
        Task { await load() }
    }

    func goToToday() { focus(Date()) }

    /// Show the month or week holding `date` and select its day; loads when
    /// that changes the range on screen (October's grid holds November 1, but
    /// November's grid is a different range). `load: false` when the caller
    /// loads right after. Returns whether the range needs loading.
    @discardableResult
    func focus(_ date: Date, load shouldLoad: Bool = true) -> Bool {
        let day = calendar.startOfDay(for: date)
        anchor = day
        selectedDay = day
        let stale = needsLoad
        if stale && shouldLoad { Task { await load() } }
        return stale
    }

    private func firstOfMonth(_ date: Date) -> Date {
        calendar.date(from: calendar.dateComponents([.year, .month], from: date)) ?? date
    }

    // MARK: Loading

    func load() async {
        let days = visibleDays
        guard let first = days.first, let last = days.last,
              let end = calendar.date(byAdding: .day, value: 1, to: last) else { return }
        loadGeneration &+= 1
        let generation = loadGeneration
        isLoading = true
        defer { if generation == loadGeneration { isLoading = false } }
        await backend.reportTimeZoneIfNeeded()
        do {
            let feed = try await backend.feed(from: first, to: end)
            guard generation == loadGeneration else { return }
            apply(feed, from: first, through: last)
            errorMessage = nil
            hasLoaded = true
            if loadedRange != first...last { loadedRange = first...last }
        } catch {
            guard generation == loadGeneration else { return }
            errorMessage = error.localizedDescription
        }
    }

    private func apply(_ feed: MWCalendarFeed, from first: Date, through last: Date) {
        var all: [CalendarEntry] = []
        all += feed.events.compactMap { CalendarEntry(event: $0, calendar: calendar) }
        all += (feed.apple?.events ?? []).compactMap { CalendarEntry(apple: $0, calendar: calendar) }
        appleStatus = feed.apple?.status ?? "not_connected"
        all += feed.google.events.compactMap { CalendarEntry(google: $0, calendar: calendar) }
        all += feed.todos.compactMap { CalendarEntry(todo: $0, calendar: calendar) }
        entries = all
        googleFeed = feed.google
        var index: [Date: [CalendarEntry]] = [:]
        for entry in all {
            for day in entry.days(in: calendar, within: first, through: last) {
                index[day, default: []].append(entry)
            }
        }
        for key in index.keys { index[key]?.sort(by: Self.order) }
        byDay = index
    }

    /// All-day first (events, then to-dos), then timed by start.
    private static func order(_ a: CalendarEntry, _ b: CalendarEntry) -> Bool {
        func rank(_ e: CalendarEntry) -> Int { e.isTodo ? 1 : (e.allDay ? 0 : 2) }
        if rank(a) != rank(b) { return rank(a) < rank(b) }
        if a.start != b.start { return a.start < b.start }
        return a.title.localizedCaseInsensitiveCompare(b.title) == .orderedAscending
    }

    func entries(on day: Date) -> [CalendarEntry] {
        byDay[calendar.startOfDay(for: day)] ?? []
    }

    // MARK: Edits

    /// Write the draft, then show its day: a December event saved from
    /// October's grid opens December, not an empty October agenda.
    func save(_ draft: CalendarDraft, editing id: String?) async throws {
        let fields = draft.fields(calendar: calendar)
        if let id {
            _ = try await backend.updateEvent(id: id, fields)
        } else {
            _ = try await backend.createEvent(fields, sourceKind: "manual", sourceRef: nil, sourceLabel: nil)
        }
        focus(draft.start, load: false)
        await load()
    }

    func delete(_ event: MWCalendarEvent) async throws {
        try await backend.deleteEvent(id: event.id)
        await load()
    }

    /// Drag an Espresso event to another day; its time of day and length stay.
    /// Sends only the new times, so a title or note changed elsewhere since
    /// this view loaded is not written back over.
    func move(_ event: MWCalendarEvent, to day: Date) async {
        guard var draft = CalendarDraft(event: event, calendar: calendar) else { return }
        let target = calendar.startOfDay(for: day)
        let from = calendar.startOfDay(for: draft.start)
        guard let delta = calendar.dateComponents([.day], from: from, to: target).day, delta != 0 else { return }
        draft.start = calendar.date(byAdding: .day, value: delta, to: draft.start) ?? draft.start
        draft.end = calendar.date(byAdding: .day, value: delta, to: draft.end) ?? draft.end
        let fields = draft.fields(calendar: calendar)
        do {
            _ = try await backend.moveEvent(id: event.id, start: fields.start, end: fields.end ?? fields.start)
            selectedDay = target
            await load()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func toggle(_ todo: MWCalendarTodo) async {
        do {
            _ = try await MatchaWorkService.shared.moveProductivityCard(
                id: todo.id, column: todo.isDone ? "todo" : "done")
            await load()
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

/// An event being written: in the editor, or one row of the email sheet.
struct CalendarDraft: Identifiable, Equatable {
    let id = UUID()
    var include = true
    var title: String
    var allDay: Bool
    var start: Date
    var end: Date
    var location: String = ""
    var notes: String = ""
    /// The email sheet: this one matches an event the email already added,
    /// so it starts unticked.
    var alreadyOnCalendar = false

    init(title: String = "", allDay: Bool, start: Date, end: Date, location: String = "", notes: String = "") {
        self.title = title
        self.allDay = allDay
        self.start = start
        self.end = end
        self.location = location
        self.notes = notes
    }

    /// A new event on `day` at `hour` o'clock: the next whole hour when that's
    /// today, else 9:00. The hour is a clock reading, the one the week grid's
    /// row is labelled with, not hours elapsed since midnight (which a DST
    /// change shifts by one).
    init(on day: Date, hour: Int? = nil, title: String = "", calendar: Calendar = .current, now: Date = Date()) {
        let base = calendar.startOfDay(for: day)
        var startHour = hour ?? 9
        if hour == nil, calendar.isDate(day, inSameDayAs: now) {
            startHour = min(23, calendar.component(.hour, from: now) + 1)
        }
        let start = calendar.date(bySettingHour: startHour, minute: 0, second: 0, of: base) ?? base
        self.init(title: title, allDay: false, start: start, end: start.addingTimeInterval(3600))
    }

    init?(event: MWCalendarEvent, calendar: Calendar = .current) {
        guard let s = CalendarWire.date(event.start, calendar: calendar),
              let e = CalendarWire.date(event.end, calendar: calendar) else { return nil }
        self.init(title: event.title, allDay: event.allDay, start: s, end: max(s, e),
                  location: event.location ?? "", notes: event.notes ?? "")
    }

    init?(suggestion: MWEmailCalendarSuggestion, calendar: Calendar = .current) {
        guard let s = CalendarWire.date(suggestion.start, calendar: calendar) else { return nil }
        let e = CalendarWire.date(suggestion.end, calendar: calendar) ?? s
        self.init(title: suggestion.title, allDay: suggestion.allDay, start: s, end: max(s, e),
                  location: suggestion.location ?? "", notes: suggestion.notes ?? "")
    }

    var trimmedTitle: String { title.trimmingCharacters(in: .whitespacesAndNewlines) }

    /// The draft with its start moved to `next`, keeping its length: whole
    /// calendar days for an all-day event (both ends stay at local midnight;
    /// March 7-9 across the spring change is still three days), elapsed time
    /// for a timed one.
    func movingStart(to next: Date, calendar: Calendar = .current) -> CalendarDraft {
        var moved = self
        if allDay {
            let days = calendar.dateComponents(
                [.day], from: calendar.startOfDay(for: start), to: calendar.startOfDay(for: end)).day ?? 0
            moved.start = calendar.startOfDay(for: next)
            moved.end = calendar.date(byAdding: .day, value: max(0, days), to: moved.start) ?? moved.start
        } else {
            moved.start = next
            moved.end = next.addingTimeInterval(max(0, end.timeIntervalSince(start)))
        }
        return moved
    }

    /// Why this can't be saved, or nil.
    var problem: String? {
        if trimmedTitle.isEmpty { return "Add a title." }
        if allDay {
            if Calendar.current.startOfDay(for: end) < Calendar.current.startOfDay(for: start) {
                return "It ends before it starts."
            }
        } else if end < start {
            return "It ends before it starts."
        }
        return nil
    }

    func fields(calendar: Calendar = .current) -> CalendarService.EventFields {
        func clean(_ s: String) -> String? {
            let t = s.trimmingCharacters(in: .whitespacesAndNewlines)
            return t.isEmpty ? nil : t
        }
        return CalendarService.EventFields(
            title: trimmedTitle,
            start: allDay ? CalendarWire.dayString(start, calendar: calendar)
                : CalendarWire.instantString(start, timeZone: calendar.timeZone),
            end: allDay ? CalendarWire.dayString(end, calendar: calendar)
                : CalendarWire.instantString(end, timeZone: calendar.timeZone),
            location: clean(location),
            notes: clean(notes)
        )
    }

    static func == (a: CalendarDraft, b: CalendarDraft) -> Bool {
        a.id == b.id && a.include == b.include && a.title == b.title && a.allDay == b.allDay
            && a.start == b.start && a.end == b.end && a.location == b.location && a.notes == b.notes
            && a.alreadyOnCalendar == b.alreadyOnCalendar
    }
}
