import SwiftUI

private enum SchedulePage: Hashable {
    case mine, team
}

/// Whether the Next shift card knows the answer. A failed fetch must not
/// read as "nothing scheduled".
enum UpcomingState: Equatable {
    case loading, loaded, failed
}

struct ScheduleView: View {
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
    @State private var upcoming: [ScheduleShift] = []
    @State private var upcomingState: UpcomingState = .loading
    /// Learned from the store; shift times are its clock face.
    @State private var storeTimeZone: TimeZone?
    @State private var selectedShift: ScheduleShift?
    @State private var loading = false
    @State private var error: String?
    @State private var focusedDay: String?
    /// Which way the last week change went, for the slide direction.
    @State private var travel: Edge = .trailing

    private var week: Date { WallClock.weekStart(containing: anchorDay, weekStartWeekday: weekStartWeekday) }

    private var displayed: [ScheduleShift] {
        let shifts = page == .mine ? (snapshot?.mine ?? []) : (snapshot?.team ?? [])
        return shifts.sorted { $0.starts_at < $1.starts_at }
    }

    private var openShifts: [ScheduleShift] {
        (snapshot?.open ?? []).sorted { $0.starts_at < $1.starts_at }
    }

    private var zone: TimeZone { storeTimeZone ?? .current }

    /// Tints the background. The card picks its own shift inside its
    /// minute timer, so it never shows a shift that already ended.
    private var nextShiftTone: DayPart? {
        ScheduleService.nextShift(in: upcoming, now: WallClock.now(timeZone: zone))
            .map { DayPart(wallClockISO: $0.starts_at) }
    }

    private var groupedDays: [(key: String, shifts: [ScheduleShift])] {
        let groups = Dictionary(grouping: displayed) { WallClock.dayKey($0.starts_at) }
        return groups.keys.sorted().map { ($0, groups[$0] ?? []) }
    }

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    NextShiftCard(
                        upcoming: upcoming,
                        state: upcomingState,
                        locations: snapshot?.locations ?? [:],
                        timeZone: zone,
                        onOpen: { selectedShift = $0 },
                        onRetry: { Task { await loadUpcoming() } }
                    )
                    .rise()

                    VStack(spacing: 12) {
                        WeekPill(
                            week: week,
                            onPrevious: { move(by: -1) },
                            onNext: { move(by: 1) }
                        )
                        DayStrip(
                            days: WallClock.days(of: week),
                            today: WallClock.dayKey(WallClock.today(timeZone: zone)),
                            shifts: displayed,
                            focused: focusedDay
                        ) { key in
                            focusedDay = key
                            withAnimation(.spring(response: 0.45, dampingFraction: 0.9)) {
                                proxy.scrollTo(key, anchor: .top)
                            }
                        }
                        GlassSegmented(
                            options: [(SchedulePage.mine, "My shifts"), (SchedulePage.team, "Team")],
                            selection: $page
                        )
                    }
                    .rise(delay: 0.06)

                    if let error {
                        ErrorBanner(message: error)
                    }

                    weekContent
                        // Prefixed: the first day's section is `.id(dayKey)`
                        // for scrollTo, and the two must not collide.
                        .id("week-" + WallClock.dayKey(week))
                        .transition(.asymmetric(
                            insertion: .move(edge: travel).combined(with: .opacity),
                            removal: .opacity
                        ))
                }
                .padding(.horizontal, Metrics.gutter)
                .padding(.top, 4)
                .padding(.bottom, 36)
            }
            .scrollIndicators(.hidden)
        }
        .ambientBackground(nextShiftTone)
        .navigationTitle("Schedule")
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button {
                    let today = WallClock.today(timeZone: zone)
                    travel = today < anchorDay ? .leading : .trailing
                    withAnimation(.spring(response: 0.45, dampingFraction: 0.88)) { anchorDay = today }
                } label: {
                    Text("Today").font(TypeScale.callout)
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
                        ((snapshot?.mine.contains(where: { $0.id == shift.id }) ?? false)
                         || upcoming.contains(where: { $0.id == shift.id }) ? .mine : .team),
                    onChanged: { await reload(); await loadUpcoming() }
                )
            }
            .presentationDetents([.medium, .large])
            .presentationDragIndicator(.visible)
            .presentationCornerRadius(32)
        }
    }

    @ViewBuilder
    private var weekContent: some View {
        VStack(alignment: .leading, spacing: 22) {
            if loading && snapshot == nil {
                ForEach(0..<3, id: \.self) { index in
                    GlassPlaceholder(leading: .bar, lineWidths: [90, 160, 120], label: "Loading shifts").rise(delay: Double(index) * 0.05)
                }
            } else if displayed.isEmpty && (page == .team || openShifts.isEmpty) {
                GlassMessage(
                    symbol: page == .mine ? "cup.and.saucer" : "person.3",
                    title: page == .mine ? "Nothing scheduled this week" : "No team shifts this week",
                    message: page == .mine
                        ? "Pick up an open shift when one is posted, or check another week."
                        : "Published shifts at your store will show up here."
                )
                .rise(delay: 0.1)
            } else {
                ForEach(Array(groupedDays.enumerated()), id: \.element.key) { index, day in
                    VStack(alignment: .leading, spacing: 10) {
                        DayHeader(key: day.key, today: WallClock.dayKey(WallClock.today(timeZone: zone)))
                        ForEach(day.shifts) { shift in
                            Button { selectedShift = shift } label: {
                                ShiftCard(
                                    shift: shift,
                                    location: snapshot?.locations[shift.location_id ?? ""],
                                    showsCrew: page == .team,
                                    employeeID: profile.id
                                )
                            }
                            .buttonStyle(PressableStyle())
                            .accessibilityIdentifier("shift.row")
                        }
                    }
                    .id(day.key)
                    .rise(delay: 0.08 + Double(index) * 0.05)
                }
                if page == .mine && !openShifts.isEmpty {
                    VStack(alignment: .leading, spacing: 10) {
                        SectionTitle(title: "Open shifts", trailing: "\(openShifts.count) available")
                        ForEach(openShifts) { shift in
                            Button { selectedShift = shift } label: {
                                ShiftCard(
                                    shift: shift,
                                    location: snapshot?.locations[shift.location_id ?? ""],
                                    showsCrew: false,
                                    employeeID: profile.id,
                                    isOpen: true
                                )
                            }
                            .buttonStyle(PressableStyle())
                            .accessibilityIdentifier("shift.row")
                        }
                    }
                    .rise(delay: 0.15)
                }
            }
        }
    }

    private func move(by weeks: Int) {
        travel = weeks > 0 ? .trailing : .leading
        focusedDay = nil
        withAnimation(.spring(response: 0.45, dampingFraction: 0.88)) {
            anchorDay = WallClock.move(anchorDay, by: weeks)
        }
    }

    private func reload() async {
        let requested = week
        loading = true
        error = nil
        defer { if requested == week { loading = false } }
        do {
            let loaded = try await ScheduleService.load(week: requested)
            // Last request wins: a slow load for a week the employee already
            // navigated away from must not replace what is on screen.
            guard requested == week else { return }
            withAnimation(.easeOut(duration: 0.2)) { snapshot = loaded }
            if let learnedZone = loaded.storeTimeZone { storeTimeZone = learnedZone }
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
            withAnimation(.spring(response: 0.5, dampingFraction: 0.85)) {
                upcoming = shifts
                upcomingState = .loaded
            }
        } catch {
            guard !error.isCancellation else { return }
            // Say so rather than show "nothing scheduled": an employee could
            // believe they have no shifts when the request simply failed.
            // Keep any shifts already shown from an earlier load.
            if upcoming.isEmpty { upcomingState = .failed }
        }
    }
}

// MARK: - Next shift

private struct NextShiftCard: View {
    let upcoming: [ScheduleShift]
    let state: UpcomingState
    let locations: [String: String]
    let timeZone: TimeZone
    let onOpen: (ScheduleShift) -> Void
    let onRetry: () -> Void

    var body: some View {
        // The shift is chosen on every tick, so the card moves on to the next
        // one the minute a shift ends instead of counting down to the past.
        TimelineView(.periodic(from: .now, by: 60)) { context in
            let now = WallClock.now(context.date, timeZone: timeZone)
            if let shift = ScheduleService.nextShift(in: upcoming, now: now) {
                Button { onOpen(shift) } label: { filled(shift, now: now) }
                    .buttonStyle(PressableStyle())
                    .accessibilityIdentifier("schedule.next")
            } else {
                switch state {
                case .loading:
                    message(symbol: "clock", tint: Palette.inkFaint, title: "Checking your next shift",
                            detail: "One moment.")
                        .redacted(reason: .placeholder)
                case .failed:
                    message(symbol: "exclamationmark.arrow.circlepath", tint: Palette.amber,
                            title: "Couldn't load your next shift",
                            detail: "Your week below is unaffected. Tap to try again.")
                        .onTapGesture(perform: onRetry)
                        .accessibilityAddTraits(.isButton)
                        .accessibilityIdentifier("schedule.next.retry")
                case .loaded:
                    message(symbol: "moon.zzz.fill", tint: Palette.dusk, title: "Nothing in the next four weeks",
                            detail: "New shifts appear here as soon as they're published.")
                }
            }
        }
    }

    private func message(symbol: String, tint: Color, title: String, detail: String) -> some View {
        HStack(spacing: 14) {
            Image(systemName: symbol)
                .font(.system(size: 22, weight: .semibold))
                .foregroundStyle(tint)
                .frame(width: 48, height: 48)
                .background(tint.opacity(0.14), in: Circle())
            VStack(alignment: .leading, spacing: 4) {
                Eyebrow("Next shift")
                Text(title).font(TypeScale.headline).foregroundStyle(Palette.ink)
                Text(detail).font(TypeScale.subhead).foregroundStyle(Palette.inkSoft)
            }
            Spacer(minLength: 0)
        }
        .padding(18)
        .glassSurface(cornerRadius: Metrics.heroRadius)
        .contentShape(Rectangle())
    }

    private func filled(_ shift: ScheduleShift, now: Date) -> some View {
        let part = DayPart(wallClockISO: shift.starts_at)
        let location = locations[shift.location_id ?? ""]
        return Group {
            let start = WallClock.date(shift.starts_at) ?? now
            let end = WallClock.date(shift.ends_at) ?? now
            let onNow = start <= now && now < end
            VStack(alignment: .leading, spacing: 14) {
                HStack(alignment: .center) {
                    Label {
                        Text("\(onNow ? "On now" : "Next shift") · \(WallClock.label(shift.starts_at, format: "EEE, MMM d"))".uppercased())
                            .font(TypeScale.eyebrow).tracking(1.4)
                    } icon: {
                        Image(systemName: part.symbol)
                    }
                    .foregroundStyle(part.color)
                    Spacer()
                    Text(onNow ? "until \(WallClock.label(shift.ends_at, format: "h:mm a"))"
                               : WallClock.countdown(to: start, from: now))
                        .font(TypeScale.caption)
                        .foregroundStyle(Palette.ink)
                        .padding(.horizontal, 10).padding(.vertical, 5)
                        .glassControl(in: Capsule(), interactive: false)
                        .contentTransition(.numericText())
                }
                Text("\(WallClock.label(shift.starts_at, format: "h:mm")) – \(WallClock.label(shift.ends_at, format: "h:mm a"))")
                    .font(TypeScale.clock)
                    .monospacedDigit()
                    .foregroundStyle(Palette.ink)
                    .minimumScaleFactor(0.7)
                    .lineLimit(1)
                HStack(spacing: 8) {
                    Text(shift.title).font(TypeScale.callout).foregroundStyle(Palette.ink)
                    if let location {
                        Text("·").foregroundStyle(Palette.inkFaint)
                        Text(location).font(TypeScale.subhead).foregroundStyle(Palette.inkSoft).lineLimit(1)
                    }
                    Spacer(minLength: 0)
                    if let duration = WallClock.duration(from: shift.starts_at, to: shift.ends_at) {
                        Text(duration).font(TypeScale.caption).foregroundStyle(Palette.inkSoft)
                    }
                }
                if onNow {
                    ShiftProgress(fraction: end > start ? now.timeIntervalSince(start) / end.timeIntervalSince(start) : 0,
                                  color: part.color)
                }
            }
            .padding(20)
            .background(alignment: .topTrailing) {
                // The day part's light, glowing through the glass.
                Image(systemName: part.symbol)
                    .font(.system(size: 120, weight: .regular))
                    .foregroundStyle(part.color.opacity(0.16))
                    .blur(radius: 1)
                    .offset(x: 28, y: -18)
                    .accessibilityHidden(true)
            }
            .clipShape(RoundedRectangle(cornerRadius: Metrics.heroRadius, style: .continuous))
            .glassSurface(cornerRadius: Metrics.heroRadius, tint: part.color)
        }
        .accessibilityElement(children: .combine)
    }
}

private struct ShiftProgress: View {
    let fraction: Double
    let color: Color

    var body: some View {
        GeometryReader { proxy in
            ZStack(alignment: .leading) {
                Capsule().fill(Palette.ink.opacity(0.08))
                Capsule().fill(LinearGradient(colors: [color.opacity(0.7), color], startPoint: .leading, endPoint: .trailing))
                    .frame(width: max(8, proxy.size.width * min(max(fraction, 0), 1)))
                    .shadow(color: color.opacity(0.5), radius: 6)
            }
        }
        .frame(height: 6)
        .accessibilityLabel("Shift progress")
        .accessibilityValue("\(Int(fraction * 100)) percent")
    }
}

// MARK: - Week navigation

private struct WeekPill: View {
    let week: Date
    let onPrevious: () -> Void
    let onNext: () -> Void

    private var label: String {
        let end = WallClock.move(week, by: 1).addingTimeInterval(-86_400)
        let sameMonth = WallClock.format(week, "MMM") == WallClock.format(end, "MMM")
        return "\(WallClock.format(week, "MMM d")) – \(WallClock.format(end, sameMonth ? "d" : "MMM d"))"
    }

    var body: some View {
        HStack(spacing: 0) {
            chevron("chevron.left", label: "Previous week", id: "week.previous", action: onPrevious)
            Spacer()
            VStack(spacing: 2) {
                Eyebrow("Week of")
                Text(label)
                    .font(TypeScale.headline)
                    .foregroundStyle(Palette.ink)
                    .contentTransition(.numericText())
                    .monospacedDigit()
            }
            Spacer()
            chevron("chevron.right", label: "Next week", id: "week.next", action: onNext)
        }
        .padding(6)
        .glassControl(in: Capsule(), interactive: false)
        .sensoryFeedback(.selection, trigger: week)
    }

    private func chevron(_ symbol: String, label: String, id: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: symbol)
                .font(.system(size: 15, weight: .semibold))
                .foregroundStyle(Palette.ink)
                .frame(width: 44, height: 44)
                .background(Palette.thumb.opacity(0.7), in: Circle())
        }
        .buttonStyle(PressableStyle())
        .accessibilityLabel(label)
        .accessibilityIdentifier(id)
    }
}

/// The week as seven days; each day shows a dot per shift in its day-part
/// light. Tapping a day scrolls to it.
private struct DayStrip: View {
    let days: [Date]
    /// Today's day key on the store's clock.
    let today: String
    let shifts: [ScheduleShift]
    let focused: String?
    let onSelect: (String) -> Void
    @Namespace private var namespace

    var body: some View {
        HStack(spacing: 4) {
            ForEach(days, id: \.self) { day in
                let key = WallClock.dayKey(day)
                let parts = shifts.filter { WallClock.dayKey($0.starts_at) == key }
                    .map { DayPart(wallClockISO: $0.starts_at) }
                let isToday = key == today
                let isFocused = key == (focused ?? today)
                Button { if !parts.isEmpty { onSelect(key) } } label: {
                    VStack(spacing: 6) {
                        Text(WallClock.format(day, "EEEEE"))
                            .font(TypeScale.eyebrow)
                            .foregroundStyle(isToday ? Palette.leaf : Palette.inkFaint)
                        Text(WallClock.format(day, "d"))
                            .font(.inter(17, isToday ? .bold : .semibold, relativeTo: .headline))
                            .foregroundStyle(parts.isEmpty && !isToday ? Palette.inkSoft : Palette.ink)
                            .monospacedDigit()
                        HStack(spacing: 3) {
                            ForEach(Array(parts.prefix(3).enumerated()), id: \.offset) { _, part in
                                Circle().fill(part.color).frame(width: 5, height: 5)
                            }
                        }
                        .frame(height: 5)
                    }
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 10)
                    .background {
                        if isFocused {
                            RoundedRectangle(cornerRadius: 16, style: .continuous)
                                .fill(Palette.thumb.opacity(0.9))
                                .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous)
                                    .strokeBorder(isToday ? Palette.leaf.opacity(0.6) : Color.clear, lineWidth: 1.2))
                                .shadow(color: Palette.shadow.opacity(0.10), radius: 8, y: 3)
                                .matchedGeometryEffect(id: "focus", in: namespace)
                        }
                    }
                }
                .buttonStyle(PressableStyle())
                .accessibilityLabel("\(WallClock.format(day, "EEEE, MMMM d")), \(parts.count) shift\(parts.count == 1 ? "" : "s")")
            }
        }
        .padding(6)
        .glassSurface(cornerRadius: Metrics.cardRadius, elevated: false)
        .animation(.spring(response: 0.4, dampingFraction: 0.85), value: focused)
    }
}

private struct DayHeader: View {
    let key: String
    let today: String

    var body: some View {
        let date = WallClock.date("\(key)T00:00:00Z") ?? Date()
        let isToday = key == today
        HStack(spacing: 8) {
            Text(WallClock.format(date, "EEEE"))
                .font(TypeScale.title)
                .foregroundStyle(Palette.ink)
            Text(WallClock.format(date, "MMM d"))
                .font(TypeScale.callout)
                .foregroundStyle(Palette.inkSoft)
            if isToday { StatusPill(text: "Today", color: Palette.leaf) }
            Spacer()
        }
        .padding(.horizontal, 4)
        .padding(.top, 2)
    }
}

// MARK: - Shift card

struct ShiftCard: View {
    let shift: ScheduleShift
    let location: String?
    var showsCrew = false
    var employeeID: String?
    var isOpen = false

    private var part: DayPart { DayPart(wallClockISO: shift.starts_at) }

    var body: some View {
        HStack(alignment: .top, spacing: 14) {
            Capsule()
                .fill(part.gradient)
                .frame(width: 4)
                .shadow(color: part.color.opacity(0.5), radius: 4)
            VStack(alignment: .leading, spacing: 2) {
                Text(WallClock.label(shift.starts_at, format: "h:mm a"))
                    .font(TypeScale.headline).monospacedDigit()
                    .foregroundStyle(Palette.ink)
                Text(WallClock.label(shift.ends_at, format: "h:mm a"))
                    .font(TypeScale.subhead).monospacedDigit()
                    .foregroundStyle(Palette.inkSoft)
                if let duration = WallClock.duration(from: shift.starts_at, to: shift.ends_at) {
                    Text(duration).font(TypeScale.caption).foregroundStyle(Palette.inkFaint).padding(.top, 4)
                }
            }
            .frame(width: 78, alignment: .leading)
            VStack(alignment: .leading, spacing: 6) {
                HStack(spacing: 6) {
                    Text(shift.title).font(TypeScale.headline).foregroundStyle(Palette.ink).lineLimit(1)
                    Spacer(minLength: 4)
                    Image(systemName: "chevron.right")
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(Palette.inkFaint)
                }
                if let location {
                    Label(location, systemImage: "mappin.and.ellipse")
                        .font(TypeScale.subhead).foregroundStyle(Palette.inkSoft).lineLimit(1)
                        .labelStyle(TightLabel())
                }
                HStack(spacing: 6) {
                    if isOpen {
                        StatusPill(text: "Open seat", color: Palette.leaf)
                    } else {
                        Label(part.label, systemImage: part.symbol)
                            .font(TypeScale.caption)
                            .foregroundStyle(part.color)
                            .labelStyle(TightLabel())
                    }
                    if shift.has_conflict == true {
                        StatusPill(text: "Overlaps your shift", color: Palette.amber)
                    }
                }
                if showsCrew && !shift.assignments.isEmpty {
                    CrewRow(assignments: shift.assignments, employeeID: employeeID)
                        .padding(.top, 2)
                }
            }
        }
        .padding(16)
        .glassSurface(tint: isOpen ? Palette.leaf : nil)
        .overlay {
            if isOpen {
                RoundedRectangle(cornerRadius: Metrics.cardRadius, style: .continuous)
                    .strokeBorder(Palette.leaf.opacity(0.55), style: StrokeStyle(lineWidth: 1.2, dash: [5, 4]))
            }
        }
        .contentShape(RoundedRectangle(cornerRadius: Metrics.cardRadius, style: .continuous))
    }
}

struct CrewRow: View {
    let assignments: [ShiftAssignment]
    var employeeID: String?

    var body: some View {
        HStack(spacing: 8) {
            HStack(spacing: -8) {
                ForEach(assignments.prefix(4)) { person in
                    Avatar(name: person.name, size: 24)
                }
            }
            Text(names).font(TypeScale.caption).foregroundStyle(Palette.inkSoft).lineLimit(1)
        }
    }

    private var names: String {
        let first = assignments.map { $0.employee_id == employeeID ? "You" : ($0.name.split(separator: " ").first.map(String.init) ?? $0.name) }
        return first.count > 3 ? first.prefix(3).joined(separator: ", ") + " +\(first.count - 3)" : first.joined(separator: ", ")
    }
}

struct TightLabel: LabelStyle {
    func makeBody(configuration: Configuration) -> some View {
        HStack(spacing: 5) {
            configuration.icon.font(.system(size: 11, weight: .semibold))
            configuration.title
        }
    }
}
