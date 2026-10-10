import SwiftUI

/// One store's week as its manager runs it: every shift, drafts included,
/// who is on each, the seats still open, and publishing.
struct ManagerWeekView: View {
    @Environment(AppState.self) private var appState
    let scope: ManagerScope
    let location: ManagedLocation
    @State private var anchorDay: Date
    @State private var week: ManagerWeek?
    /// The week `week` belongs to; another week's rows are never shown under this one's label.
    @State private var loadedWeek: Date?
    @State private var jobs: [ScheduleJob] = []
    @State private var error: String?
    @State private var notice: String?
    /// The one sheet this screen presents, by what it shows.
    @State private var sheet: WeekSheet?
    @State private var confirmPublish = false
    @State private var publishing = false

    init(scope: ManagerScope, location: ManagedLocation) {
        self.scope = scope
        self.location = location
        _anchorDay = State(initialValue: WallClock.today(timeZone: location.timeZone ?? .current))
    }

    private var zone: TimeZone { location.timeZone ?? .current }
    private var weekStart: Date {
        WallClock.weekStart(containing: anchorDay, weekStartWeekday: location.week_start_weekday)
    }
    private var current: ManagerWeek? { loadedWeek == weekStart ? week : nil }
    private var shifts: [ScheduleShift] { (current?.shifts ?? []).sorted { $0.starts_at < $1.starts_at } }
    private var todayKey: String { WallClock.dayKey(WallClock.today(timeZone: zone)) }

    /// A store manager cannot change a shift with no store; it shows read-only.
    private func canEdit(_ shift: ScheduleShift) -> Bool { scope.company_wide || shift.location_id != nil }

    /// What "Publish week" would publish: this store's drafts (and, for a
    /// business admin, ones with no store, which the server includes too).
    private var draftCount: Int {
        shifts.filter { $0.status == "draft" && ($0.location_id == location.id || scope.company_wide) }.count
    }
    private var openSeats: Int { shifts.reduce(0) { $0 + $1.openSeats } }

    private var groupedDays: [(key: String, shifts: [ScheduleShift])] {
        let groups = Dictionary(grouping: shifts) { WallClock.dayKey($0.starts_at) }
        return groups.keys.sorted().map { ($0, groups[$0] ?? []) }
    }

    var body: some View {
        ScrollViewReader { proxy in
            List {
                if let error {
                    ErrorRow(message: error) { Task { await reload() } }.cardRow()
                }
                if let notice {
                    Label(notice, systemImage: "checkmark.circle.fill")
                        .font(.app(.subheadline))
                        .foregroundStyle(Color.brand)
                        .cardRow()
                }
                if current != nil {
                    summaryRow.bareRow(top: 4, bottom: 0)
                }
                content
            }
            .listStyle(.plain)
            .safeAreaInset(edge: .top, spacing: 0) {
                WeekHeader(
                    week: weekStart,
                    today: todayKey,
                    shifts: shifts,
                    onPrevious: { move(by: -1) },
                    onNext: { move(by: 1) },
                    onSelect: { key in withAnimation { proxy.scrollTo(key, anchor: .top) } }
                )
                .padding(.horizontal, 12)
                .padding(.vertical, 4)
                .glassPanel(in: RoundedRectangle(cornerRadius: 26, style: .continuous))
                .padding(.horizontal, 16)
                .padding(.bottom, 8)
            }
        }
        .appBackdrop()
        .toolbar {
            ToolbarItemGroup(placement: .topBarTrailing) {
                if draftCount > 0 {
                    Button {
                        confirmPublish = true
                    } label: {
                        if publishing { ProgressView() } else { Text("Publish (\(draftCount))") }
                    }
                    .disabled(publishing)
                    .accessibilityIdentifier("week.publish")
                }
                if scope.features.assistant {
                    Button {
                        sheet = .assistant
                    } label: {
                        Label("Ask Huume", systemImage: "sparkles")
                    }
                    .accessibilityIdentifier("week.huume")
                }
                Button {
                    sheet = .newShift(day: defaultNewShiftDay)
                } label: {
                    Label("Add shift", systemImage: "plus")
                }
                .accessibilityIdentifier("week.addShift")
            }
        }
        .confirmationDialog(
            "Publish \(draftCount) shift\(draftCount == 1 ? "" : "s")?",
            isPresented: $confirmPublish, titleVisibility: .visible
        ) {
            Button("Publish") { Task { await publish() } }
        } message: {
            Text("Everyone scheduled is notified, and the shifts show up in their app.")
        }
        .refreshable { await reload() }
        .task(id: "\(location.id)|\(WallClock.dayKey(weekStart))") { await reload() }
        .sheet(item: $sheet) { item in
            NavigationStack {
                switch item {
                case .shift(let id):
                    if let shift = current?.shifts.first(where: { $0.id == id }) {
                        ManagerShiftDetailView(
                            shift: shift,
                            weekShifts: shifts,
                            roster: current?.roster ?? [],
                            jobs: jobs,
                            location: location,
                            weekStart: weekStart,
                            canEdit: canEdit(shift),
                            onChanged: { await reload() }
                        )
                    } else {
                        ContentUnavailableView("Shift removed", systemImage: "calendar.badge.minus")
                    }
                case .newShift(let day):
                    ShiftEditorView(
                        mode: .create(day: day), location: location, jobs: jobs,
                        onSaved: { await reload() }
                    )
                case .assistant:
                    HuumeChatView(location: location, weekStart: weekStart) { await reload() }
                }
            }
        }
    }

    @ViewBuilder
    private var content: some View {
        if current == nil {
            ForEach(0..<3, id: \.self) { _ in
                ShiftRow(shift: Self.placeholder, location: nil, showsChevron: false)
                    .redacted(reason: .placeholder)
                    .cardRow()
            }
        } else if shifts.isEmpty {
            VStack(spacing: 12) {
                ContentUnavailableView(
                    "Nothing scheduled", systemImage: "calendar",
                    description: Text("Add this week's shifts, then publish them to your crew.")
                )
                Button("Add a shift") { sheet = .newShift(day: defaultNewShiftDay) }
                    .buttonStyle(.borderedProminent)
            }
            .bareRow(top: 24, bottom: 8)
        } else {
            ForEach(groupedDays, id: \.key) { day in
                SectionLabel(dayTitle(day.key)).id(day.key)
                ForEach(day.shifts) { shift in
                    Button { sheet = .shift(id: shift.id) } label: {
                        ManagerShiftRow(shift: shift, editable: canEdit(shift))
                    }
                    .cardRow()
                    .accessibilityIdentifier("week.shift")
                }
            }
        }
    }

    private var summaryRow: some View {
        HStack(spacing: 8) {
            Text("\(shifts.count) shift\(shifts.count == 1 ? "" : "s")")
            if draftCount > 0 { StatusPill(text: "\(draftCount) draft\(draftCount == 1 ? "" : "s")", color: .orange) }
            if openSeats > 0 { StatusPill(text: "\(openSeats) open seat\(openSeats == 1 ? "" : "s")", color: .brand) }
            Spacer()
        }
        .font(.app(.subheadline))
        .foregroundStyle(Color.secondary)
        .padding(.horizontal, 4)
    }

    /// Today when it is in the week on screen, else the week's first day.
    private var defaultNewShiftDay: String {
        let days = WallClock.days(of: weekStart).map(WallClock.dayKey)
        return days.contains(todayKey) ? todayKey : (days.first ?? todayKey)
    }

    private func dayTitle(_ key: String) -> String {
        let date = WallClock.date("\(key)T00:00:00Z") ?? Date()
        let title = WallClock.format(date, "EEEE, MMM d")
        return key == todayKey ? "Today · \(title)" : title
    }

    private func move(by weeks: Int) {
        notice = nil
        withAnimation { anchorDay = WallClock.move(weekStart, by: weeks) }
    }

    private func reload() async {
        let requested = weekStart
        error = nil
        do {
            async let loadedWeekData = ManagerService.week(location: location.id, starting: requested)
            async let loadedJobs = ManagerService.jobs(location: location.id)
            let (newWeek, newJobs) = try await (loadedWeekData, loadedJobs)
            guard requested == weekStart else { return }
            week = newWeek
            jobs = newJobs
            loadedWeek = requested
        } catch {
            if !error.isCancellation { self.error = error.localizedDescription }
        }
    }

    private func publish() async {
        publishing = true
        error = nil
        notice = nil
        defer { publishing = false }
        do {
            let count = try await ManagerService.publishWeek(location: location.id, starting: weekStart)
            notice = "Published \(count) shift\(count == 1 ? "" : "s"). Your crew has been notified."
            await reload()
        } catch {
            // Usually the store is not set up to publish yet; the server says what is missing.
            self.error = error.localizedDescription
        }
    }

    private static let placeholder = ScheduleShift(
        id: "placeholder", location_id: nil, role: "Barista", department: nil,
        starts_at: "2026-01-01T09:00:00Z", ends_at: "2026-01-01T17:00:00Z", break_minutes: nil,
        notes: nil, status: "draft", assignments: [], has_conflict: nil,
        job_id: nil, required_staff: 1, published_at: nil
    )
}

private enum WeekSheet: Identifiable {
    case shift(id: String)
    /// A new shift on this calendar day ("2026-10-12").
    case newShift(day: String)
    case assistant

    var id: String {
        switch self {
        case .shift(let id): "shift-\(id)"
        case .newShift(let day): "new-\(day)"
        case .assistant: "assistant"
        }
    }
}

/// A shift on the manager's week: when, the crew, and what still needs doing.
private struct ManagerShiftRow: View {
    let shift: ScheduleShift
    let editable: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            ShiftRow(shift: shift, location: nil, showsCrew: true)
            HStack(spacing: 6) {
                if shift.status == "draft" { StatusPill(text: "Draft", color: .orange) }
                if shift.status == "cancelled" { StatusPill(text: "Cancelled", color: .secondary) }
                if shift.openSeats > 0 {
                    StatusPill(text: "\(shift.openSeats) open", color: .brand)
                }
                if !editable { StatusPill(text: "No store", color: .secondary) }
            }
            .padding(.leading, 40)
        }
        // The whole card opens the shift, gaps included.
        .contentShape(Rectangle())
    }
}
