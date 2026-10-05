import SwiftUI

private enum SchedulePage: Hashable {
    case mine, team
}

/// Whether the Next shift row knows the answer. A failed fetch must not
/// read as "nothing scheduled".
enum UpcomingState: Equatable {
    case loading, loaded, failed
}

struct ScheduleView: View {
    @Environment(AppState.self) private var appState
    let profile: EmployeeProfile
    /// A day inside the week on screen. The week is always derived from it, so
    /// learning the store's week start re-aligns around the day the employee
    /// was looking at. Aligning the previously shown Sunday instead put a
    /// Monday-start store one week back on six days out of seven.
    @State private var anchorDay = WallClock.today()
    /// Learned from the store on first load; until then Sunday.
    @State private var weekStartWeekday = 0
    @State private var page: SchedulePage = .mine
    @State private var snapshot: ScheduleSnapshot?
    /// The week `snapshot` belongs to. While another week loads, its rows are
    /// replaced by placeholders rather than shown under the new week's label.
    @State private var snapshotWeek: Date?
    @State private var upcoming: [ScheduleShift] = []
    @State private var upcomingState: UpcomingState = .loading
    /// Learned from the store; shift times are its clock face.
    @State private var storeTimeZone: TimeZone?
    @State private var selectedShift: ScheduleShift?
    @State private var error: String?

    private var week: Date { WallClock.weekStart(containing: anchorDay, weekStartWeekday: weekStartWeekday) }

    private var current: ScheduleSnapshot? { snapshotWeek == week ? snapshot : nil }

    private var displayed: [ScheduleShift] {
        let shifts = page == .mine ? (current?.mine ?? []) : (current?.team ?? [])
        return shifts.sorted { $0.starts_at < $1.starts_at }
    }

    private var openShifts: [ScheduleShift] {
        (current?.open ?? []).sorted { $0.starts_at < $1.starts_at }
    }

    private var zone: TimeZone { storeTimeZone ?? .current }

    private var todayKey: String { WallClock.dayKey(WallClock.today(timeZone: zone)) }

    private var groupedDays: [(key: String, shifts: [ScheduleShift])] {
        let groups = Dictionary(grouping: displayed) { WallClock.dayKey($0.starts_at) }
        return groups.keys.sorted().map { ($0, groups[$0] ?? []) }
    }

    var body: some View {
        ScrollViewReader { proxy in
            // The next shift is chosen on every tick, so the row moves on the
            // minute a shift ends instead of counting down to the past.
            TimelineView(.periodic(from: .now, by: 60)) { context in
                List {
                    nextShift(now: WallClock.now(context.date, timeZone: zone))

                    if let error {
                        ErrorRow(message: error) { Task { await reload() } }.cardRow()
                    }

                    weekContent
                }
                .listStyle(.plain)
                // The week floats over the shifts, which scroll beneath it.
                .safeAreaInset(edge: .top, spacing: 0) {
                    VStack(spacing: 10) {
                        WeekHeader(
                            week: week,
                            today: todayKey,
                            shifts: displayed,
                            onPrevious: { move(by: -1) },
                            onNext: { move(by: 1) },
                            onSelect: { key in withAnimation { proxy.scrollTo(key, anchor: .top) } }
                        )
                        Picker("Whose shifts", selection: $page) {
                            Text("My shifts").tag(SchedulePage.mine)
                            Text("Team").tag(SchedulePage.team)
                        }
                        .pickerStyle(.segmented)
                    }
                    .padding(.horizontal, 12)
                    .padding(.top, 4)
                    .padding(.bottom, 12)
                    .glassPanel(in: RoundedRectangle(cornerRadius: 26, style: .continuous))
                    .padding(.horizontal, 16)
                    .padding(.bottom, 8)
                }
            }
        }
        .appBackdrop()
        .navigationTitle("Schedule")
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button("Today") {
                    withAnimation { anchorDay = WallClock.today(timeZone: zone) }
                }
                .accessibilityIdentifier("schedule.today")
            }
        }
        .refreshable { await reload(); await loadUpcoming() }
        .task(id: week) { await reload() }
        .task { await loadUpcoming() }
        .sheet(item: $selectedShift) { shift in
            NavigationStack {
                ShiftDetailView(
                    shift: shift, location: snapshot?.locations[shift.location_id ?? ""],
                    employeeID: profile.id,
                    mode: openShifts.contains(where: { $0.id == shift.id }) ? .open :
                        ((current?.mine.contains(where: { $0.id == shift.id }) ?? false)
                         || upcoming.contains(where: { $0.id == shift.id }) ? .mine : .team),
                    onChanged: { await reload(); await loadUpcoming() }
                )
            }
            .presentationDetents([.medium, .large])
            .presentationDragIndicator(.visible)
        }
    }

    // MARK: Next shift

    /// Shown when there is one, or when the answer could not be loaded. An
    /// employee with nothing coming up already sees that in the week below.
    @ViewBuilder
    private func nextShift(now: Date) -> some View {
        if let shift = ScheduleService.nextShift(in: upcoming, now: now) {
            Button { selectedShift = shift } label: {
                GlassHero {
                    NextShiftRow(shift: shift, now: now, location: snapshot?.locations[shift.location_id ?? ""])
                }
            }
            .buttonStyle(.plain)
            .bareRow(top: 8, bottom: 8)
            .accessibilityIdentifier("schedule.next")
        } else if upcomingState == .failed {
            VStack(alignment: .leading, spacing: 8) {
                Label("Couldn't load your next shift. Your week below is unaffected.",
                      systemImage: "exclamationmark.arrow.circlepath")
                    .font(.app(.subheadline))
                    .foregroundStyle(Color.secondary)
                Button("Try again") { Task { await loadUpcoming() } }
                    .buttonStyle(.borderless)
                    .accessibilityIdentifier("schedule.next.retry")
            }
            .cardRow()
        }
    }

    // MARK: Week

    @ViewBuilder
    private var weekContent: some View {
        if current == nil && error == nil {
            ForEach(0..<3, id: \.self) { _ in
                VStack(alignment: .leading, spacing: 3) {
                    Text("9:00 AM – 5:00 PM").font(.app(.headline))
                    Text("Role · Store name").font(.app(.subheadline))
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .redacted(reason: .placeholder)
                .cardRow()
                .accessibilityLabel("Loading shifts")
            }
        } else if current != nil && displayed.isEmpty && (page == .team || openShifts.isEmpty) {
            ContentUnavailableView(
                page == .mine ? "Nothing scheduled this week" : "No team shifts this week",
                systemImage: page == .mine ? "calendar" : "person.3",
                description: Text(page == .mine
                    ? "Pick up an open shift when one is posted, or check another week."
                    : "Published shifts at your store will show up here.")
            )
            .bareRow(top: 24)
        } else {
            ForEach(groupedDays, id: \.key) { day in
                Text(dayTitle(day.key))
                    .font(.app(.title3))
                    .bareRow(top: 14, bottom: 2)
                    .id(day.key)
                ForEach(day.shifts) { shift in
                    Button { selectedShift = shift } label: {
                        ShiftRow(
                            shift: shift,
                            location: current?.locations[shift.location_id ?? ""],
                            showsCrew: page == .team,
                            employeeID: profile.id
                        )
                    }
                    .cardRow()
                    .accessibilityIdentifier("shift.row")
                }
            }
            if page == .mine && !openShifts.isEmpty {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Open shifts").font(.app(.title3))
                    Text("Claim one and your manager approves it.")
                        .font(.app(.subheadline)).foregroundStyle(Color.secondary)
                }
                .bareRow(top: 14, bottom: 2)
                ForEach(openShifts) { shift in
                    Button { selectedShift = shift } label: {
                        ShiftRow(
                            shift: shift,
                            location: current?.locations[shift.location_id ?? ""],
                            showsDay: true,
                            isOpen: true
                        )
                    }
                    .cardRow()
                    .accessibilityIdentifier("shift.row")
                }
            }
        }
    }

    private func dayTitle(_ key: String) -> String {
        let date = WallClock.date("\(key)T00:00:00Z") ?? Date()
        let title = WallClock.format(date, "EEEE, MMM d")
        return key == todayKey ? "Today · \(title)" : title
    }

    private func move(by weeks: Int) {
        withAnimation { anchorDay = WallClock.move(anchorDay, by: weeks) }
    }

    private func reload() async {
        let requested = week
        error = nil
        do {
            let loaded = try await ScheduleService.load(week: requested)
            // Last request wins: a slow load for a week the employee already
            // navigated away from must not replace what is on screen.
            guard requested == week else { return }
            withAnimation(.easeOut(duration: 0.2)) {
                snapshot = loaded
                snapshotWeek = requested
            }
            if let learnedZone = loaded.storeTimeZone {
                storeTimeZone = learnedZone
                appState.storeTimeZone = learnedZone
            }
            error = nil
            if let learned = loaded.weekStartWeekday, learned != weekStartWeekday {
                // A Monday-start store: re-derive the week from the anchor day.
                // `week` changes, which re-runs the task for the aligned week.
                weekStartWeekday = learned
            }
        } catch {
            // A superseded load is cancelled by `.task(id:)`; that is not a
            // failure the employee should see.
            guard !error.isCancellation, requested == week else { return }
            self.error = error.localizedDescription
        }
    }

    private func loadUpcoming() async {
        if upcoming.isEmpty { upcomingState = .loading }
        do {
            let shifts = try await ScheduleService.upcoming(from: WallClock.today(timeZone: zone))
            withAnimation {
                upcoming = shifts
                upcomingState = .loaded
            }
        } catch {
            guard !error.isCancellation else { return }
            // Say so rather than show nothing: an employee could believe they
            // have no shifts when the request simply failed. Keep any shifts
            // already shown from an earlier load.
            if upcoming.isEmpty { upcomingState = .failed }
        }
    }
}

// MARK: - Week header

/// The week's range with previous and next, over its seven days. Each day
/// shows a dot per shift in its day-part color; tapping a day with shifts
/// scrolls to it.
private struct WeekHeader: View {
    let week: Date
    /// Today's day key on the store's clock.
    let today: String
    let shifts: [ScheduleShift]
    let onPrevious: () -> Void
    let onNext: () -> Void
    let onSelect: (String) -> Void

    private var label: String {
        let end = WallClock.move(week, by: 1).addingTimeInterval(-86_400)
        let sameMonth = WallClock.format(week, "MMM") == WallClock.format(end, "MMM")
        return "\(WallClock.format(week, "MMM d")) – \(WallClock.format(end, sameMonth ? "d" : "MMM d"))"
    }

    var body: some View {
        VStack(spacing: 8) {
            HStack {
                chevron("chevron.left", label: "Previous week", id: "week.previous", action: onPrevious)
                Spacer()
                Text(label)
                    .font(.app(.headline))
                    .monospacedDigit()
                    .contentTransition(.numericText())
                Spacer()
                chevron("chevron.right", label: "Next week", id: "week.next", action: onNext)
            }
            HStack(spacing: 0) {
                ForEach(WallClock.days(of: week), id: \.self) { day in
                    dayCell(day)
                }
            }
        }
        .buttonStyle(.borderless)
        .sensoryFeedback(.selection, trigger: week)
    }

    private func chevron(_ symbol: String, label: String, id: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: symbol)
                .fontWeight(.semibold)
                .frame(width: 44, height: 44)
                .contentShape(Rectangle())
        }
        .accessibilityLabel(label)
        .accessibilityIdentifier(id)
    }

    private func dayCell(_ day: Date) -> some View {
        let key = WallClock.dayKey(day)
        let parts = shifts.filter { WallClock.dayKey($0.starts_at) == key }
            .map { DayPart(wallClockISO: $0.starts_at) }
        let isToday = key == today
        return Button { onSelect(key) } label: {
            VStack(spacing: 4) {
                Text(WallClock.format(day, "EEEEE"))
                    .font(.app(.caption2, .semibold))
                    .foregroundStyle(Color.secondary)
                Text(WallClock.format(day, "d"))
                    .font(.app(.body, isToday ? .semibold : .regular))
                    .monospacedDigit()
                    .foregroundStyle(isToday ? Color.white : parts.isEmpty ? Color.secondary : Color.primary)
                    .frame(width: 34, height: 34)
                    .background { if isToday { Circle().fill(Color.brand) } }
                HStack(spacing: 3) {
                    ForEach(Array(parts.prefix(3).enumerated()), id: \.offset) { _, part in
                        Circle().fill(part.color).frame(width: 5, height: 5)
                    }
                }
                .frame(height: 5)
            }
            .frame(maxWidth: .infinity)
            .contentShape(Rectangle())
        }
        .allowsHitTesting(!parts.isEmpty)
        .accessibilityLabel("\(WallClock.format(day, "EEEE, MMMM d")), \(parts.count) shift\(parts.count == 1 ? "" : "s")")
    }
}

// MARK: - Rows

private struct NextShiftRow: View {
    let shift: ScheduleShift
    let now: Date
    let location: String?

    var body: some View {
        let part = DayPart(wallClockISO: shift.starts_at)
        let start = WallClock.date(shift.starts_at) ?? now
        let end = WallClock.date(shift.ends_at) ?? now
        let onNow = start <= now && now < end
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: part.symbol)
                .font(.app(.title3))
                .foregroundStyle(part.color)
                .frame(width: 28)
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 4) {
                HStack(alignment: .firstTextBaseline) {
                    Text(onNow ? "On now" : WallClock.label(shift.starts_at, format: "EEEE, MMM d"))
                    Spacer(minLength: 8)
                    Text(onNow ? "until \(WallClock.label(shift.ends_at, format: "h:mm a"))"
                               : WallClock.countdown(to: start, from: now))
                        .monospacedDigit()
                        .contentTransition(.numericText())
                }
                .font(.app(.subheadline))
                .foregroundStyle(Color.secondary)
                Text("\(WallClock.label(shift.starts_at, format: "h:mm a")) – \(WallClock.label(shift.ends_at, format: "h:mm a"))")
                    .font(.app(.title2, .bold))
                    .monospacedDigit()
                    .foregroundStyle(Color.primary)
                    .minimumScaleFactor(0.7)
                    .lineLimit(1)
                Text([shift.title, location].compactMap { $0 }.joined(separator: " · "))
                    .font(.app(.subheadline))
                    .foregroundStyle(Color.secondary)
                    .lineLimit(1)
                if onNow {
                    ProgressView(value: end > start ? min(max(now.timeIntervalSince(start) / end.timeIntervalSince(start), 0), 1) : 0)
                        .tint(part.color)
                        .padding(.top, 4)
                        .accessibilityLabel("Shift progress")
                }
            }
        }
        .padding(.vertical, 4)
        .accessibilityElement(children: .combine)
    }
}

/// One shift in a list: when, what and where, with the day part's symbol.
struct ShiftRow: View {
    let shift: ScheduleShift
    let location: String?
    var showsCrew = false
    var employeeID: String?
    /// For lists that are not grouped by day.
    var showsDay = false
    var isOpen = false
    var showsChevron = true

    private var part: DayPart { DayPart(wallClockISO: shift.starts_at) }

    private var detail: String {
        // The store name is the long part, so it goes last and takes the truncation.
        [shift.title, WallClock.duration(from: shift.starts_at, to: shift.ends_at), location]
            .compactMap { $0 }.joined(separator: " · ")
    }

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: part.symbol)
                .foregroundStyle(part.color)
                .frame(width: 28)
                .accessibilityLabel(part.label)
            VStack(alignment: .leading, spacing: 3) {
                if showsDay {
                    Text(WallClock.label(shift.starts_at, format: "EEEE, MMM d"))
                        .font(.app(.subheadline))
                        .foregroundStyle(Color.secondary)
                }
                Text("\(WallClock.label(shift.starts_at, format: "h:mm a")) – \(WallClock.label(shift.ends_at, format: "h:mm a"))")
                    .font(.app(.headline))
                    .monospacedDigit()
                    .foregroundStyle(Color.primary)
                Text(detail)
                    .font(.app(.subheadline))
                    .foregroundStyle(Color.secondary)
                    .lineLimit(1)
                if isOpen || shift.has_conflict == true {
                    HStack(spacing: 6) {
                        if isOpen { StatusPill(text: "Open", color: .brand) }
                        if shift.has_conflict == true { StatusPill(text: "Overlaps your shift", color: .orange) }
                    }
                    .padding(.top, 2)
                }
                if showsCrew && !shift.assignments.isEmpty {
                    CrewRow(assignments: shift.assignments, employeeID: employeeID)
                        .padding(.top, 2)
                }
            }
            Spacer(minLength: 4)
            if showsChevron {
                Image(systemName: "chevron.right")
                    .font(.app(.footnote, .semibold))
                    .foregroundStyle(Color(.tertiaryLabel))
                    .accessibilityHidden(true)
            }
        }
    }
}

struct CrewRow: View {
    let assignments: [ShiftAssignment]
    var employeeID: String?

    var body: some View {
        HStack(spacing: 8) {
            HStack(spacing: -6) {
                ForEach(assignments.prefix(4)) { person in
                    Avatar(name: person.name, size: 22)
                }
            }
            Text(names).font(.app(.caption)).foregroundStyle(Color.secondary).lineLimit(1)
        }
    }

    private var names: String {
        let first = assignments.map { $0.employee_id == employeeID ? "You" : ($0.name.split(separator: " ").first.map(String.init) ?? $0.name) }
        return first.count > 3 ? first.prefix(3).joined(separator: ", ") + " +\(first.count - 3)" : first.joined(separator: ", ")
    }
}
