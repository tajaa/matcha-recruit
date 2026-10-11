import Foundation

/// One thing on the calendar view, whatever it came from.
struct CalendarEntry: Identifiable, Hashable {
    enum Kind: Hashable {
        case espresso(MWCalendarEvent)
        case google(MWGoogleCalendarEvent)
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
        case .todo: return nil
        }
    }

    init?(event: MWCalendarEvent) {
        guard let s = CalendarWire.date(event.start), let e = CalendarWire.date(event.end) else { return nil }
        self.init(id: "e:\(event.id)", kind: .espresso(event), title: event.title,
                  start: s, end: max(s, e), allDay: event.allDay)
    }

    init?(google: MWGoogleCalendarEvent) {
        guard let s = CalendarWire.date(google.start) else { return nil }
        let e = google.end.flatMap(CalendarWire.date) ?? s
        self.init(id: "g:\(google.id)", kind: .google(google), title: google.title,
                  start: s, end: max(s, e), allDay: google.allDay)
    }

    init?(todo: MWCalendarTodo) {
        guard let d = CalendarWire.day(todo.dueDate) else { return nil }
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

    /// The local days this entry shows on (a timed event ending exactly at
    /// midnight does not spill into the next day).
    func days(in calendar: Calendar, limit: Int = 62) -> [Date] {
        let first = calendar.startOfDay(for: start)
        var lastInstant = end
        if !allDay, end > start, calendar.startOfDay(for: end) == end { lastInstant = end.addingTimeInterval(-1) }
        let last = calendar.startOfDay(for: lastInstant)
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
    private(set) var anchor: Date = Date()
    var selectedDay: Date = Calendar.current.startOfDay(for: Date())

    private(set) var entries: [CalendarEntry] = []
    private(set) var byDay: [Date: [CalendarEntry]] = [:]
    /// ok | partial | not_connected | needs_permission | error | skipped
    private(set) var googleStatus = "skipped"
    private(set) var isLoading = false
    private(set) var hasLoaded = false
    /// First day of the range the last successful load covered. Changes only
    /// when a different range arrives, not on a reload after an edit.
    private(set) var loadedRangeStart: Date?
    var errorMessage: String?

    @ObservationIgnored private var loadGeneration = 0

    var calendar: Calendar { .current }

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

    /// Show the month or week holding `date` and select its day. `load: false`
    /// when the caller loads right after.
    func focus(_ date: Date, load shouldLoad: Bool = true) {
        let day = calendar.startOfDay(for: date)
        let reload = !visibleDays.contains(day) || !hasLoaded
        anchor = day
        selectedDay = day
        if reload && shouldLoad { Task { await load() } }
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
        await CalendarService.shared.reportTimeZoneIfNeeded()
        do {
            let feed = try await CalendarService.shared.feed(from: first, to: end)
            guard generation == loadGeneration else { return }
            apply(feed)
            errorMessage = nil
            hasLoaded = true
            if loadedRangeStart != first { loadedRangeStart = first }
        } catch {
            guard generation == loadGeneration else { return }
            errorMessage = error.localizedDescription
        }
    }

    private func apply(_ feed: MWCalendarFeed) {
        var all: [CalendarEntry] = []
        all += feed.events.compactMap(CalendarEntry.init(event:))
        all += feed.google.events.compactMap(CalendarEntry.init(google:))
        all += feed.todos.compactMap(CalendarEntry.init(todo:))
        entries = all
        googleStatus = feed.google.status
        var index: [Date: [CalendarEntry]] = [:]
        for entry in all {
            for day in entry.days(in: calendar) { index[day, default: []].append(entry) }
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

    func save(_ draft: CalendarDraft, editing id: String?) async throws {
        if let id {
            _ = try await CalendarService.shared.updateEvent(id: id, draft.fields())
        } else {
            _ = try await CalendarService.shared.createEvent(draft.fields())
        }
        selectedDay = calendar.startOfDay(for: draft.start)
        await load()
    }

    func delete(_ event: MWCalendarEvent) async throws {
        try await CalendarService.shared.deleteEvent(id: event.id)
        await load()
    }

    /// Drag an Espresso event to another day; its time of day and length stay.
    func move(_ event: MWCalendarEvent, to day: Date) async {
        guard var draft = CalendarDraft(event: event) else { return }
        let target = calendar.startOfDay(for: day)
        let from = calendar.startOfDay(for: draft.start)
        guard let delta = calendar.dateComponents([.day], from: from, to: target).day, delta != 0 else { return }
        draft.start = calendar.date(byAdding: .day, value: delta, to: draft.start) ?? draft.start
        draft.end = calendar.date(byAdding: .day, value: delta, to: draft.end) ?? draft.end
        do {
            try await save(draft, editing: event.id)
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

    init(title: String = "", allDay: Bool, start: Date, end: Date, location: String = "", notes: String = "") {
        self.title = title
        self.allDay = allDay
        self.start = start
        self.end = end
        self.location = location
        self.notes = notes
    }

    /// A new event on `day`: the next whole hour when that's today, else 9:00.
    init(on day: Date, hour: Int? = nil, title: String = "", calendar: Calendar = .current) {
        let base = calendar.startOfDay(for: day)
        var startHour = hour ?? 9
        if hour == nil, calendar.isDateInToday(day) {
            startHour = min(23, calendar.component(.hour, from: Date()) + 1)
        }
        let start = calendar.date(byAdding: .hour, value: startHour, to: base) ?? base
        self.init(title: title, allDay: false, start: start, end: start.addingTimeInterval(3600))
    }

    init?(event: MWCalendarEvent) {
        guard let s = CalendarWire.date(event.start), let e = CalendarWire.date(event.end) else { return nil }
        self.init(title: event.title, allDay: event.allDay, start: s, end: max(s, e),
                  location: event.location ?? "", notes: event.notes ?? "")
    }

    init?(suggestion: MWEmailCalendarSuggestion) {
        guard let s = CalendarWire.date(suggestion.start) else { return nil }
        let e = CalendarWire.date(suggestion.end) ?? s
        self.init(title: suggestion.title, allDay: suggestion.allDay, start: s, end: max(s, e),
                  location: suggestion.location ?? "", notes: suggestion.notes ?? "")
    }

    var trimmedTitle: String { title.trimmingCharacters(in: .whitespacesAndNewlines) }

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

    func fields() -> CalendarService.EventFields {
        func clean(_ s: String) -> String? {
            let t = s.trimmingCharacters(in: .whitespacesAndNewlines)
            return t.isEmpty ? nil : t
        }
        return CalendarService.EventFields(
            title: trimmedTitle,
            start: allDay ? CalendarWire.dayString(start) : CalendarWire.instantString(start),
            end: allDay ? CalendarWire.dayString(end) : CalendarWire.instantString(end),
            location: clean(location),
            notes: clean(notes)
        )
    }

    static func == (a: CalendarDraft, b: CalendarDraft) -> Bool {
        a.id == b.id && a.include == b.include && a.title == b.title && a.allDay == b.allDay
            && a.start == b.start && a.end == b.end && a.location == b.location && a.notes == b.notes
    }
}
