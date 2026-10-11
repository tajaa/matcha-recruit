import SwiftUI
import AppKit

/// The Calendar tab: the person's Espresso calendar, their dated to-dos and,
/// when connected, their Google Calendar (read-only), in a month or week view
/// with the selected day's agenda beside it. Espresso (the assistant) and the
/// email reader write to the same calendar.
struct CalendarWorkspace: View {
    @Environment(AppState.self) private var appState
    @State private var vm = CalendarViewModel()
    @State private var editor: CalendarEditorRequest?
    @State private var connectingGoogle = false
    @AppStorage("calendar.mode") private var storedMode = CalendarViewModel.Mode.month.rawValue

    var body: some View {
        VStack(spacing: 0) {
            CalendarHeader(vm: vm, connectingGoogle: connectingGoogle,
                           onNew: { newEvent(on: vm.selectedDay) },
                           onConnectGoogle: connectGoogle)
            Divider().opacity(0.2)
            if let error = vm.errorMessage, vm.hasLoaded {
                errorBanner(error)
            }
            if !vm.hasLoaded && vm.errorMessage != nil {
                loadFailed
            } else {
                HStack(spacing: 0) {
                    Group {
                        switch vm.mode {
                        case .month:
                            CalendarMonthGrid(vm: vm, onOpen: open, onNew: { newEvent(on: $0) })
                        case .week:
                            CalendarWeekGrid(vm: vm, onOpen: open, onNew: { day, hour in newEvent(on: day, hour: hour) })
                        }
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    Divider().opacity(0.2)
                    CalendarDayPanel(vm: vm, onOpen: open, onNew: { newEvent(on: vm.selectedDay) })
                        .frame(width: 290)
                }
            }
        }
        .background(ThemeRadialBackground())
        .task {
            vm.mode = CalendarViewModel.Mode(rawValue: storedMode) ?? .month
            if let date = appState.calendarFocusDate {
                appState.calendarFocusDate = nil
                vm.focus(date, load: false)
            }
            await vm.load()
        }
        .onChange(of: vm.mode) { _, mode in storedMode = mode.rawValue }
        .onChange(of: appState.calendarFocusDate) { _, date in
            guard let date else { return }
            appState.calendarFocusDate = nil
            vm.focus(date)
        }
        // Back from the browser after connecting Google: show it.
        .onReceive(NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification)) { _ in
            if connectingGoogle {
                connectingGoogle = false
                Task { await vm.load() }
            }
        }
        .sheet(item: $editor) { request in
            CalendarEventEditor(
                request: request,
                onSave: { draft in try await vm.save(draft, editing: request.event?.id) },
                onDelete: deleteAction(for: request.event)
            )
        }
    }

    // MARK: Actions

    private func deleteAction(for event: MWCalendarEvent?) -> (() async throws -> Void)? {
        guard let event else { return nil }
        return { try await vm.delete(event) }
    }

    private func newEvent(on day: Date, hour: Int? = nil) {
        vm.selectedDay = Calendar.current.startOfDay(for: day)
        editor = CalendarEditorRequest(event: nil, draft: CalendarDraft(on: day, hour: hour))
    }

    private func open(_ entry: CalendarEntry) {
        vm.selectedDay = Calendar.current.startOfDay(for: entry.start)
        switch entry.kind {
        case .espresso(let event):
            if let draft = CalendarDraft(event: event) {
                editor = CalendarEditorRequest(event: event, draft: draft)
            }
        case .google(let event):
            if let raw = event.link, let url = URL(string: raw), url.scheme == "https" {
                NSWorkspace.shared.open(url)
            }
        case .todo(let todo):
            Task { await vm.toggle(todo) }
        }
    }

    private func connectGoogle() {
        Task {
            do {
                let raw = try await MatchaWorkService.shared.connectGoogle(forAbility: "calendar")
                if let url = URL(string: raw) {
                    connectingGoogle = true
                    NSWorkspace.shared.open(url)
                }
            } catch {
                vm.errorMessage = error.localizedDescription
            }
        }
    }

    // MARK: States

    private func errorBanner(_ text: String) -> some View {
        HStack(spacing: 6) {
            Image(systemName: "exclamationmark.triangle.fill").font(.system(size: 10))
            Text(text).font(.system(size: 11)).lineLimit(2)
            Spacer()
            Button("Retry") { Task { await vm.load() } }
                .buttonStyle(.plain).font(.system(size: 11, weight: .semibold))
            Button { vm.errorMessage = nil } label: { Image(systemName: "xmark").font(.system(size: 9, weight: .bold)) }
                .buttonStyle(.plain)
        }
        .foregroundColor(.orange)
        .padding(.horizontal, 16).padding(.vertical, 6)
        .background(Color.orange.opacity(0.08))
    }

    private var loadFailed: some View {
        VStack(spacing: 10) {
            Image(systemName: "calendar.badge.exclamationmark")
                .font(.system(size: 30))
                .foregroundColor(appState.themeTextSecondary.opacity(0.7))
            Text("Couldn't load your calendar")
                .font(.system(size: 13, weight: .semibold))
                .foregroundColor(appState.themeText)
            Text(vm.errorMessage ?? "")
                .font(.system(size: 11))
                .foregroundColor(appState.themeTextSecondary)
                .multilineTextAlignment(.center)
                .frame(maxWidth: 360)
            Button("Try again") { Task { await vm.load() } }
                .buttonStyle(.borderedProminent)
                .tint(appState.themeAccent)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

struct CalendarEditorRequest: Identifiable {
    let id = UUID()
    let event: MWCalendarEvent?
    let draft: CalendarDraft
}

// MARK: - Colors

enum CalendarPalette {
    static let google = Color(red: 0.30, green: 0.55, blue: 0.95)

    static func color(_ entry: CalendarEntry, accent: Color, secondary: Color) -> Color {
        switch entry.kind {
        case .espresso: return accent
        case .google: return google
        case .todo: return secondary
        }
    }
}

// MARK: - Header

private struct CalendarHeader: View {
    @Environment(AppState.self) private var appState
    let vm: CalendarViewModel
    let connectingGoogle: Bool
    let onNew: () -> Void
    let onConnectGoogle: () -> Void

    var body: some View {
        HStack(spacing: 10) {
            Text(vm.title)
                .font(.system(size: 18, weight: .bold))
                .foregroundColor(appState.themeText)
                .frame(minWidth: 170, alignment: .leading)
            HStack(spacing: 2) {
                navButton("chevron.left", help: "Previous (⌘←)") { vm.shift(-1) }
                    .keyboardShortcut(.leftArrow, modifiers: .command)
                Button("Today") { vm.goToToday() }
                    .buttonStyle(.plain)
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundColor(appState.themeText)
                    .padding(.horizontal, 9).padding(.vertical, 4)
                    .background(RoundedRectangle(cornerRadius: 5).stroke(appState.themeBorder, lineWidth: 1))
                    .keyboardShortcut("t", modifiers: .command)
                    .help("Today (⌘T)")
                navButton("chevron.right", help: "Next (⌘→)") { vm.shift(1) }
                    .keyboardShortcut(.rightArrow, modifiers: .command)
            }
            if vm.isLoading {
                ProgressView().controlSize(.small).padding(.leading, 2)
            }
            Spacer(minLength: 12)
            googleStatus
            if appState.assistantEnabled {
                Button {
                    appState.clearPrimaryNav()
                    appState.showAssistantHub = true
                } label: {
                    Label("Ask Espresso", systemImage: "sparkles")
                        .font(.system(size: 11, weight: .medium))
                }
                .buttonStyle(.plain)
                .foregroundColor(appState.themeTextSecondary)
                .help("Ask Espresso to add, move or find things on your calendar")
            }
            Picker("", selection: Binding(get: { vm.mode }, set: { vm.setMode($0) })) {
                ForEach(CalendarViewModel.Mode.allCases) { Text($0.rawValue).tag($0) }
            }
            .pickerStyle(.segmented)
            .labelsHidden()
            .frame(width: 130)
            Button(action: onNew) {
                Label("New event", systemImage: "plus")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundColor(appState.themeOnAccent)
                    .padding(.horizontal, 10).padding(.vertical, 5)
                    .background(RoundedRectangle(cornerRadius: 6).fill(appState.themeAccent))
            }
            .buttonStyle(.plain)
            .keyboardShortcut("n", modifiers: .command)
            .help("New event (⌘N)")
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 11)
    }

    private func navButton(_ icon: String, help: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: icon)
                .font(.system(size: 11, weight: .semibold))
                .frame(width: 24, height: 22)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .foregroundColor(appState.themeTextSecondary)
        .help(help)
    }

    @ViewBuilder
    private var googleStatus: some View {
        switch vm.googleStatus {
        case "ok", "partial":
            let partial = vm.googleStatus == "partial"
            HStack(spacing: 5) {
                Circle().fill(CalendarPalette.google).frame(width: 7, height: 7)
                Text("Google Calendar").font(.system(size: 11))
                if partial {
                    Image(systemName: "exclamationmark.circle")
                        .font(.system(size: 10))
                        .foregroundColor(.orange)
                }
            }
            .foregroundColor(appState.themeTextSecondary)
            .help(partial
                  ? "Your Google Calendar has more events here than Espresso could load. Open Google Calendar for the full list."
                  : "Your Google Calendar is shown read-only. Ask Espresso to change it.")
        case "not_connected", "needs_permission":
            Button(action: onConnectGoogle) {
                Label(connectingGoogle ? "Waiting for Google…" : "Show Google Calendar",
                      systemImage: "link")
                    .font(.system(size: 11, weight: .medium))
            }
            .buttonStyle(.plain)
            .foregroundColor(appState.themeTextSecondary)
            .disabled(connectingGoogle)
            .help(vm.googleStatus == "needs_permission"
                  ? "Allow calendar access on your Google connection"
                  : "Connect your Google account to see its calendar here")
        case "error":
            Label("Google Calendar unavailable", systemImage: "exclamationmark.triangle")
                .font(.system(size: 11))
                .foregroundColor(.orange)
        default:
            EmptyView()
        }
    }
}

// MARK: - Month

private struct CalendarMonthGrid: View {
    @Environment(AppState.self) private var appState
    let vm: CalendarViewModel
    let onOpen: (CalendarEntry) -> Void
    let onNew: (Date) -> Void

    private let spacing: CGFloat = 1

    var body: some View {
        VStack(spacing: 0) {
            weekdayHeader
            GeometryReader { geo in
                let days = vm.visibleDays
                let rows = max(1, days.count / 7)
                let cellHeight = (geo.size.height - spacing * CGFloat(rows - 1)) / CGFloat(rows)
                VStack(spacing: spacing) {
                    ForEach(0..<rows, id: \.self) { row in
                        HStack(spacing: spacing) {
                            ForEach(days[(row * 7)..<min(days.count, row * 7 + 7)], id: \.self) { day in
                                MonthDayCell(vm: vm, day: day, height: cellHeight, onOpen: onOpen, onNew: onNew)
                            }
                        }
                    }
                }
                .background(appState.themeBorder.opacity(0.35))
            }
        }
    }

    private var weekdayHeader: some View {
        HStack(spacing: 0) {
            ForEach(weekdaySymbols, id: \.self) { symbol in
                Text(symbol.uppercased())
                    .font(.system(size: 10, weight: .semibold))
                    .tracking(0.5)
                    .foregroundColor(appState.themeTextSecondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.leading, 8)
            }
        }
        .padding(.vertical, 6)
    }

    private var weekdaySymbols: [String] {
        let cal = Calendar.current
        let syms = cal.shortStandaloneWeekdaySymbols
        let first = cal.firstWeekday - 1
        return Array(syms[first...] + syms[..<first])
    }
}

private struct MonthDayCell: View {
    @Environment(AppState.self) private var appState
    let vm: CalendarViewModel
    let day: Date
    let height: CGFloat
    let onOpen: (CalendarEntry) -> Void
    let onNew: (Date) -> Void
    @State private var dropTargeted = false

    var body: some View {
        let cal = Calendar.current
        let inMonth = vm.isInAnchorMonth(day)
        let isToday = cal.isDateInToday(day)
        let isSelected = cal.isDate(day, inSameDayAs: vm.selectedDay)
        let entries = vm.entries(on: day)
        let capacity = max(1, Int((height - 30) / 18))
        let shown = entries.count > capacity ? Array(entries.prefix(capacity - 1)) : entries

        VStack(alignment: .leading, spacing: 2) {
            HStack {
                Text("\(cal.component(.day, from: day))")
                    .font(.system(size: 11, weight: isToday ? .bold : .medium))
                    .foregroundColor(isToday ? appState.themeOnAccent
                                     : (inMonth ? appState.themeText : appState.themeTextSecondary.opacity(0.45)))
                    .frame(minWidth: 20, minHeight: 20)
                    .background(Circle().fill(isToday ? appState.themeAccent : Color.clear))
                Spacer(minLength: 0)
            }
            ForEach(shown) { entry in
                MonthChip(entry: entry, day: day, dimmed: !inMonth)
                    .onTapGesture { onOpen(entry) }
                    .modifier(DraggableEntry(entry: entry))
            }
            if entries.count > shown.count {
                Text("\(entries.count - shown.count) more")
                    .font(.system(size: 10, weight: .medium))
                    .foregroundColor(appState.themeTextSecondary)
                    .padding(.leading, 4)
            }
            Spacer(minLength: 0)
        }
        .padding(4)
        .frame(maxWidth: .infinity, minHeight: height, maxHeight: height, alignment: .topLeading)
        .background(cellBackground(inMonth: inMonth, selected: isSelected))
        .overlay(
            Rectangle().stroke(appState.themeAccent.opacity(dropTargeted ? 0.8 : (isSelected ? 0.55 : 0)),
                               lineWidth: isSelected || dropTargeted ? 1.5 : 0)
        )
        .contentShape(Rectangle())
        .onTapGesture(count: 2) { onNew(day) }
        .onTapGesture { vm.selectedDay = cal.startOfDay(for: day) }
        .dropDestination(for: String.self) { items, _ in
            guard let event = espressoEvent(items.first) else { return false }
            Task { await vm.move(event, to: day) }
            return true
        } isTargeted: { dropTargeted = $0 }
        .contextMenu {
            Button("New event on \(day.formatted(.dateTime.month(.abbreviated).day()))") { onNew(day) }
        }
    }

    private func cellBackground(inMonth: Bool, selected: Bool) -> Color {
        if selected { return appState.themeAccent.opacity(0.07) }
        return inMonth ? appState.themeBg : appState.themeBg.opacity(0.6)
    }

    private func espressoEvent(_ id: String?) -> MWCalendarEvent? {
        guard let id else { return nil }
        return vm.entries.first(where: { $0.id == id })?.espressoEvent
    }
}

/// Only Espresso events move by drag; Google and to-dos stay put.
private struct DraggableEntry: ViewModifier {
    let entry: CalendarEntry
    func body(content: Content) -> some View {
        if entry.espressoEvent != nil {
            content.draggable(entry.id)
        } else {
            content
        }
    }
}

private struct MonthChip: View {
    @Environment(AppState.self) private var appState
    let entry: CalendarEntry
    let day: Date
    let dimmed: Bool

    var body: some View {
        let color = CalendarPalette.color(entry, accent: appState.themeAccent, secondary: appState.themeTextSecondary)
        HStack(spacing: 4) {
            if entry.isTodo {
                Image(systemName: entry.isDone ? "checkmark.square.fill" : "square")
                    .font(.system(size: 9))
                    .foregroundColor(appState.themeTextSecondary)
            } else if !entry.allDay {
                Circle().fill(color).frame(width: 6, height: 6)
                Text(CalendarFormat.shortTime(entry.start, on: day))
                    .font(.system(size: 10).monospacedDigit())
                    .foregroundColor(appState.themeTextSecondary)
            }
            Text(entry.title)
                .font(.system(size: 10.5, weight: entry.allDay && !entry.isTodo ? .semibold : .regular))
                .foregroundColor(entry.isDone ? appState.themeTextSecondary : appState.themeText)
                .strikethrough(entry.isDone, color: appState.themeTextSecondary)
                .lineLimit(1)
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 4)
        .frame(height: 16)
        .background(
            RoundedRectangle(cornerRadius: 4)
                .fill(entry.allDay && !entry.isTodo ? color.opacity(0.22) : Color.clear)
        )
        .opacity(dimmed ? 0.55 : 1)
        .contentShape(Rectangle())
        .help(CalendarFormat.tooltip(entry))
    }
}

// MARK: - Week

private struct CalendarWeekGrid: View {
    @Environment(AppState.self) private var appState
    let vm: CalendarViewModel
    let onOpen: (CalendarEntry) -> Void
    let onNew: (Date, Int) -> Void

    static let hourHeight: CGFloat = 46
    static let gutter: CGFloat = 52

    var body: some View {
        let days = vm.visibleDays
        VStack(spacing: 0) {
            dayHeaders(days)
            allDayRow(days)
            Divider().opacity(0.3)
            ScrollViewReader { proxy in
                ScrollView {
                    HStack(alignment: .top, spacing: 0) {
                        hourLabels
                        ForEach(days, id: \.self) { day in
                            WeekDayColumn(vm: vm, day: day, onOpen: onOpen, onNew: onNew)
                                .frame(maxWidth: .infinity)
                        }
                    }
                    .frame(height: Self.hourHeight * 24)
                }
                // Half an hour above the first event (8 AM on an empty week),
                // so the label at the top isn't cut in half.
                .onAppear { proxy.scrollTo(max(0, firstHour(days) * 2 - 1), anchor: .top) }
                .onChange(of: vm.loadedRange) { _, _ in
                    proxy.scrollTo(max(0, firstHour(vm.visibleDays) * 2 - 1), anchor: .top)
                }
            }
        }
    }

    private func dayHeaders(_ days: [Date]) -> some View {
        HStack(spacing: 0) {
            Color.clear.frame(width: Self.gutter, height: 1)
            ForEach(days, id: \.self) { day in
                let isToday = Calendar.current.isDateInToday(day)
                HStack(spacing: 5) {
                    Text(day.formatted(.dateTime.weekday(.abbreviated)).uppercased())
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundColor(appState.themeTextSecondary)
                    Text(day.formatted(.dateTime.day()))
                        .font(.system(size: 15, weight: isToday ? .bold : .medium))
                        .foregroundColor(isToday ? appState.themeOnAccent : appState.themeText)
                        .frame(minWidth: 26, minHeight: 26)
                        .background(Circle().fill(isToday ? appState.themeAccent : Color.clear))
                }
                .frame(maxWidth: .infinity)
                .contentShape(Rectangle())
                .onTapGesture { vm.selectedDay = Calendar.current.startOfDay(for: day) }
            }
        }
        .padding(.vertical, 6)
    }

    private func allDayRow(_ days: [Date]) -> some View {
        HStack(alignment: .top, spacing: 0) {
            Text("all-day")
                .font(.system(size: 9))
                .foregroundColor(appState.themeTextSecondary)
                .frame(width: Self.gutter, alignment: .trailing)
                .padding(.trailing, 6)
                .padding(.top, 3)
            ForEach(days, id: \.self) { day in
                let items = vm.entries(on: day).filter(\.allDay)
                VStack(alignment: .leading, spacing: 2) {
                    ForEach(items.prefix(3)) { entry in
                        MonthChip(entry: entry, day: day, dimmed: false)
                            .onTapGesture { onOpen(entry) }
                    }
                    if items.count > 3 {
                        Text("\(items.count - 3) more")
                            .font(.system(size: 9))
                            .foregroundColor(appState.themeTextSecondary)
                            .onTapGesture { vm.selectedDay = Calendar.current.startOfDay(for: day) }
                    }
                }
                .frame(maxWidth: .infinity, minHeight: 22, alignment: .topLeading)
                .padding(.horizontal, 2)
            }
        }
        .padding(.bottom, 4)
    }

    private func firstHour(_ days: [Date]) -> Int {
        let cal = Calendar.current
        let starts = days.flatMap { vm.entries(on: $0) }.filter { !$0.allDay && days.contains(cal.startOfDay(for: $0.start)) }
        return starts.map { cal.component(.hour, from: $0.start) }.min().map { min($0, 8) } ?? 8
    }

    /// Half-hour rows, so the grid can be scrolled to a half hour (`id` is the
    /// half-hour index); a label sits on each hour's line.
    private var hourLabels: some View {
        VStack(spacing: 0) {
            ForEach(0..<48, id: \.self) { half in
                Group {
                    if half % 2 == 0 && half > 0 {
                        Text(CalendarFormat.hourLabel(half / 2))
                            .font(.system(size: 9.5).monospacedDigit())
                            .foregroundColor(appState.themeTextSecondary)
                            .offset(y: -6)
                    } else {
                        Color.clear
                    }
                }
                .frame(width: Self.gutter - 6, height: Self.hourHeight / 2, alignment: .topTrailing)
                .padding(.trailing, 6)
                .id(half)
            }
        }
    }
}

private struct WeekDayColumn: View {
    @Environment(AppState.self) private var appState
    let vm: CalendarViewModel
    let day: Date
    let onOpen: (CalendarEntry) -> Void
    let onNew: (Date, Int) -> Void
    @State private var dropTargeted = false

    var body: some View {
        let hourHeight = CalendarWeekGrid.hourHeight
        let isSelected = Calendar.current.isDate(day, inSameDayAs: vm.selectedDay)
        let placed = WeekLayout.place(vm.entries(on: day).filter { !$0.allDay }, on: day, hourHeight: hourHeight)
        GeometryReader { geo in
            ZStack(alignment: .topLeading) {
                VStack(spacing: 0) {
                    ForEach(0..<24, id: \.self) { _ in
                        Rectangle()
                            .fill(Color.clear)
                            .frame(height: hourHeight)
                            .overlay(alignment: .top) {
                                Rectangle().fill(appState.themeBorder.opacity(0.45)).frame(height: 0.5)
                            }
                    }
                }
                .background(isSelected ? appState.themeAccent.opacity(0.04) : Color.clear)
                .contentShape(Rectangle())
                .onTapGesture(count: 2, coordinateSpace: .local) { point in
                    onNew(day, min(23, max(0, Int(point.y / hourHeight))))
                }
                .onTapGesture { vm.selectedDay = Calendar.current.startOfDay(for: day) }

                ForEach(placed, id: \.entry.id) { item in
                    let width = (geo.size.width - 4) / CGFloat(item.columns)
                    WeekEventBlock(entry: item.entry, height: item.height)
                        .frame(width: max(10, width - 2), height: item.height)
                        .offset(x: 2 + width * CGFloat(item.column), y: item.top)
                        .onTapGesture { onOpen(item.entry) }
                        .modifier(DraggableEntry(entry: item.entry))
                }

                if Calendar.current.isDateInToday(day) {
                    NowLine(hourHeight: hourHeight)
                }
            }
            .overlay(alignment: .leading) {
                Rectangle().fill(appState.themeBorder.opacity(0.45)).frame(width: 0.5)
            }
            .overlay(Rectangle().stroke(appState.themeAccent.opacity(dropTargeted ? 0.7 : 0), lineWidth: 1.5))
        }
        .dropDestination(for: String.self) { items, _ in
            guard let id = items.first, let event = vm.entries.first(where: { $0.id == id })?.espressoEvent
            else { return false }
            Task { await vm.move(event, to: day) }
            return true
        } isTargeted: { dropTargeted = $0 }
    }
}

private struct NowLine: View {
    let hourHeight: CGFloat
    var body: some View {
        TimelineView(.periodic(from: .now, by: 60)) { context in
            let cal = Calendar.current
            let minutes = CGFloat(cal.component(.hour, from: context.date) * 60 + cal.component(.minute, from: context.date))
            HStack(spacing: 0) {
                Circle().fill(Color.red).frame(width: 7, height: 7).offset(x: -3)
                Rectangle().fill(Color.red).frame(height: 1.2)
            }
            .offset(y: minutes / 60 * hourHeight - 3.5)
        }
        .allowsHitTesting(false)
    }
}

private struct WeekEventBlock: View {
    @Environment(AppState.self) private var appState
    let entry: CalendarEntry
    let height: CGFloat

    var body: some View {
        let color = CalendarPalette.color(entry, accent: appState.themeAccent, secondary: appState.themeTextSecondary)
        HStack(spacing: 0) {
            Rectangle().fill(color).frame(width: 3)
            VStack(alignment: .leading, spacing: 1) {
                Text(entry.title)
                    .font(.system(size: 10.5, weight: .semibold))
                    .foregroundColor(appState.themeText)
                    .lineLimit(height > 40 ? 2 : 1)
                if height > 30 {
                    Text(CalendarFormat.range(entry))
                        .font(.system(size: 9.5).monospacedDigit())
                        .foregroundColor(appState.themeTextSecondary)
                        .lineLimit(1)
                }
                if height > 56, let location = entry.location, !location.isEmpty {
                    Text(location)
                        .font(.system(size: 9.5))
                        .foregroundColor(appState.themeTextSecondary)
                        .lineLimit(1)
                }
                Spacer(minLength: 0)
            }
            .padding(.horizontal, 4)
            .padding(.vertical, 2)
            Spacer(minLength: 0)
        }
        .background(RoundedRectangle(cornerRadius: 4).fill(color.opacity(0.18)))
        .clipShape(RoundedRectangle(cornerRadius: 4))
        .contentShape(Rectangle())
        .help(CalendarFormat.tooltip(entry))
    }
}

/// Places timed entries on one day of the week grid: overlapping entries
/// share the width side by side. Positions are clock readings on that day
/// (the axis the hour labels, the click-to-create hour and the now line use),
/// so a 09:00 event sits on the 9 AM line on a DST day too. Overlap is judged
/// by the height a block is drawn at, which is never less than `minHeight`.
enum WeekLayout {
    struct Placed {
        let entry: CalendarEntry
        let column: Int
        let columns: Int
        let top: CGFloat
        let height: CGFloat
    }

    static let dayMinutes: Double = 24 * 60

    /// Minutes past midnight on the clock of `day`, 0 before it, 1440 after.
    static func clockMinutes(_ date: Date, on day: Date, calendar: Calendar = .current) -> Double {
        let dayStart = calendar.startOfDay(for: day)
        guard date > dayStart else { return 0 }
        guard let dayEnd = calendar.date(byAdding: .day, value: 1, to: dayStart), date < dayEnd else {
            return dayMinutes
        }
        let c = calendar.dateComponents([.hour, .minute, .second], from: date)
        return Double((c.hour ?? 0) * 60 + (c.minute ?? 0)) + Double(c.second ?? 0) / 60
    }

    static func place(_ entries: [CalendarEntry], on day: Date, hourHeight: CGFloat,
                      minHeight: CGFloat = 18, calendar: Calendar = .current) -> [Placed] {
        let minMinutes = Double(minHeight / hourHeight) * 60
        // (entry, start, drawn end) in clock minutes.
        let spans: [(CalendarEntry, Double, Double)] = entries.map { e in
            let s = min(clockMinutes(e.start, on: day, calendar: calendar), dayMinutes - minMinutes)
            let f = max(clockMinutes(e.end, on: day, calendar: calendar), s + minMinutes)
            return (e, s, f)
        }.sorted { $0.1 == $1.1 ? $0.2 > $1.2 : $0.1 < $1.1 }

        var out: [Placed] = []
        var cluster: [(CalendarEntry, Double, Double, Int)] = []
        var columnEnds: [Double] = []
        var clusterEnd = -Double.infinity

        func flush() {
            let count = max(1, columnEnds.count)
            for (entry, s, f, column) in cluster {
                let top = CGFloat(s / 60) * hourHeight
                let height = max(minHeight, CGFloat((f - s) / 60) * hourHeight - 1)
                out.append(Placed(entry: entry, column: column, columns: count, top: top, height: height))
            }
            cluster = []
            columnEnds = []
        }

        for (entry, s, f) in spans {
            if !cluster.isEmpty && s >= clusterEnd { flush() }
            if let free = columnEnds.firstIndex(where: { $0 <= s }) {
                columnEnds[free] = f
                cluster.append((entry, s, f, free))
            } else {
                columnEnds.append(f)
                cluster.append((entry, s, f, columnEnds.count - 1))
            }
            clusterEnd = max(clusterEnd, f)
        }
        flush()
        return out
    }
}

// MARK: - Day panel

private struct CalendarDayPanel: View {
    @Environment(AppState.self) private var appState
    let vm: CalendarViewModel
    let onOpen: (CalendarEntry) -> Void
    let onNew: () -> Void

    var body: some View {
        let day = vm.selectedDay
        let entries = vm.entries(on: day)
        let allDay = entries.filter { $0.allDay && !$0.isTodo }
        let timed = entries.filter { !$0.allDay }
        let todos = entries.filter(\.isTodo)

        VStack(alignment: .leading, spacing: 0) {
            VStack(alignment: .leading, spacing: 2) {
                Text(day.formatted(.dateTime.weekday(.wide)).uppercased())
                    .font(.system(size: 10, weight: .semibold))
                    .tracking(0.6)
                    .foregroundColor(Calendar.current.isDateInToday(day) ? appState.themeAccent : appState.themeTextSecondary)
                Text(day.formatted(.dateTime.month(.wide).day()))
                    .font(.system(size: 20, weight: .bold))
                    .foregroundColor(appState.themeText)
            }
            .padding(.horizontal, 16)
            .padding(.top, 14)
            .padding(.bottom, 10)

            if entries.isEmpty {
                emptyDay
            } else {
                ScrollView {
                    VStack(alignment: .leading, spacing: 14) {
                        if !allDay.isEmpty { section("All day", allDay) }
                        if !timed.isEmpty { section("Schedule", timed) }
                        if !todos.isEmpty { section("To-dos", todos) }
                    }
                    .padding(.horizontal, 12)
                    .padding(.bottom, 12)
                }
            }
            Spacer(minLength: 0)
            footer
        }
        .background(appState.themeSidebar.opacity(0.35))
    }

    private func section(_ title: String, _ items: [CalendarEntry]) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title.uppercased())
                .font(.system(size: 9.5, weight: .semibold))
                .tracking(0.6)
                .foregroundColor(appState.themeTextSecondary)
                .padding(.horizontal, 4)
            ForEach(items) { entry in
                DayPanelRow(entry: entry, day: vm.selectedDay, onOpen: { onOpen(entry) })
            }
        }
    }

    private var emptyDay: some View {
        VStack(spacing: 8) {
            Image(systemName: "calendar")
                .font(.system(size: 24))
                .foregroundColor(appState.themeTextSecondary.opacity(0.6))
            Text("Nothing on this day")
                .font(.system(size: 12, weight: .medium))
                .foregroundColor(appState.themeTextSecondary)
            Button(action: onNew) {
                Label("New event", systemImage: "plus").font(.system(size: 11, weight: .semibold))
            }
            .buttonStyle(.plain)
            .foregroundColor(appState.themeAccent)
        }
        .frame(maxWidth: .infinity)
        .padding(.top, 36)
    }

    @ViewBuilder
    private var footer: some View {
        if appState.assistantEnabled {
            HStack(alignment: .top, spacing: 6) {
                Image(systemName: "sparkles").font(.system(size: 10)).foregroundColor(appState.themeAccent)
                Text("Ask Espresso: “put lunch with Sam on Friday at noon on my calendar”, or add events from an email in Email.")
                    .font(.system(size: 10.5))
                    .foregroundColor(appState.themeTextSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding(12)
        }
    }
}

private struct DayPanelRow: View {
    @Environment(AppState.self) private var appState
    let entry: CalendarEntry
    let day: Date
    let onOpen: () -> Void
    @State private var hovering = false

    var body: some View {
        let color = CalendarPalette.color(entry, accent: appState.themeAccent, secondary: appState.themeTextSecondary)
        HStack(alignment: .top, spacing: 8) {
            if entry.isTodo {
                Button(action: onOpen) {
                    Image(systemName: entry.isDone ? "checkmark.circle.fill" : "circle")
                        .font(.system(size: 13))
                        .foregroundColor(entry.isDone ? appState.themeAccent : appState.themeTextSecondary)
                }
                .buttonStyle(.plain)
                .help(entry.isDone ? "Mark not done" : "Mark done")
            } else {
                RoundedRectangle(cornerRadius: 1.5).fill(color).frame(width: 3)
            }
            VStack(alignment: .leading, spacing: 2) {
                Text(entry.title)
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundColor(entry.isDone ? appState.themeTextSecondary : appState.themeText)
                    .strikethrough(entry.isDone, color: appState.themeTextSecondary)
                    .lineLimit(2)
                if let line = detailLine, !line.isEmpty {
                    Text(line)
                        .font(.system(size: 10.5))
                        .foregroundColor(appState.themeTextSecondary)
                        .lineLimit(2)
                }
                if let source = sourceLine {
                    Label(source, systemImage: sourceIcon)
                        .font(.system(size: 10))
                        .foregroundColor(appState.themeTextSecondary.opacity(0.85))
                        .lineLimit(1)
                }
            }
            Spacer(minLength: 0)
            if case .google = entry.kind, hovering {
                Image(systemName: "arrow.up.right.square")
                    .font(.system(size: 10))
                    .foregroundColor(appState.themeTextSecondary)
            }
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 7)
        .background(RoundedRectangle(cornerRadius: 7).fill(appState.themeText.opacity(hovering ? 0.06 : 0.03)))
        .contentShape(Rectangle())
        .onHover { hovering = $0 }
        .onTapGesture { if !entry.isTodo { onOpen() } }
        .help(helpText)
    }

    private var detailLine: String? {
        var parts: [String] = []
        if !entry.allDay { parts.append(CalendarFormat.range(entry)) }
        if case .todo(let todo) = entry.kind { parts.append(todo.boardTitle) }
        if let location = entry.location, !location.isEmpty { parts.append(location) }
        if case .google(let g) = entry.kind, let n = g.attendeeCount, n > 0 { parts.append("\(n) invited") }
        return parts.joined(separator: " · ")
    }

    private var sourceLine: String? {
        switch entry.kind {
        case .espresso(let e):
            switch e.sourceKind {
            case "email": return "From email" + (e.sourceLabel.map { ": \($0)" } ?? "")
            case "assistant": return "Added by Espresso"
            case "journal": return "From a journal"
            default: return nil
            }
        case .google: return "Google Calendar"
        case .todo: return nil
        }
    }

    private var sourceIcon: String {
        switch entry.kind {
        case .espresso(let e): return e.sourceKind == "email" ? "envelope" : "sparkles"
        case .google: return "globe"
        case .todo: return "checklist"
        }
    }

    private var helpText: String {
        switch entry.kind {
        case .espresso: return "Open to edit"
        case .google: return "Open in Google Calendar"
        case .todo: return ""
        }
    }
}

// MARK: - Formatting

enum CalendarFormat {
    /// "9a", "3:30p" — compact, for month chips. A timed event that began
    /// before `day` shows as continuing.
    static func shortTime(_ date: Date, on day: Date) -> String {
        let cal = Calendar.current
        if !cal.isDate(date, inSameDayAs: day) { return "…" }
        let hour = cal.component(.hour, from: date)
        let minute = cal.component(.minute, from: date)
        let h12 = hour % 12 == 0 ? 12 : hour % 12
        let suffix = hour < 12 ? "a" : "p"
        return minute == 0 ? "\(h12)\(suffix)" : "\(h12):\(String(format: "%02d", minute))\(suffix)"
    }

    static func hourLabel(_ hour: Int) -> String {
        var comps = DateComponents()
        comps.hour = hour
        let date = Calendar.current.date(from: comps) ?? Date()
        return date.formatted(.dateTime.hour())
    }

    static func range(_ entry: CalendarEntry) -> String {
        if entry.allDay {
            let cal = Calendar.current
            if cal.isDate(entry.start, inSameDayAs: entry.end) { return "All day" }
            return "\(entry.start.formatted(.dateTime.month(.abbreviated).day())) – \(entry.end.formatted(.dateTime.month(.abbreviated).day()))"
        }
        let start = entry.start.formatted(date: .omitted, time: .shortened)
        if entry.end <= entry.start { return start }
        let sameDay = Calendar.current.isDate(entry.start, inSameDayAs: entry.end)
        let end = sameDay ? entry.end.formatted(date: .omitted, time: .shortened)
            : entry.end.formatted(.dateTime.month(.abbreviated).day().hour().minute())
        return "\(start) – \(end)"
    }

    static func tooltip(_ entry: CalendarEntry) -> String {
        var lines = [entry.title, range(entry)]
        if let location = entry.location, !location.isEmpty { lines.append(location) }
        return lines.joined(separator: "\n")
    }
}
