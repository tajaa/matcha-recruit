import SwiftUI

private enum SchedulePage: String, CaseIterable {
    case mine = "My shifts"
    case team = "Team"
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
    private var week: Date { WallClock.weekStart(containing: anchorDay, weekStartWeekday: weekStartWeekday) }
    @State private var page: SchedulePage = .mine
    @State private var snapshot: ScheduleSnapshot?
    @State private var selectedShift: ScheduleShift?
    @State private var loading = false
    @State private var error: String?

    private var displayed: [ScheduleShift] {
        let shifts: [ScheduleShift]
        switch page {
        case .mine: shifts = snapshot?.mine ?? []
        case .team: shifts = snapshot?.team ?? []
        }
        return shifts.sorted { $0.starts_at < $1.starts_at }
    }

    private var openShifts: [ScheduleShift] {
        (snapshot?.open ?? []).sorted { $0.starts_at < $1.starts_at }
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Button { anchorDay = WallClock.move(anchorDay, by: -1) } label: { Image(systemName: "chevron.left") }
                    .accessibilityLabel("Previous week")
                Spacer()
                VStack(spacing: 3) {
                    Text("WEEK OF").font(.caption2.bold()).tracking(2).foregroundStyle(.secondary)
                    Text(WallClock.weekLabel(week))
                        .font(.headline)
                }
                Spacer()
                Button { anchorDay = WallClock.move(anchorDay, by: 1) } label: { Image(systemName: "chevron.right") }
                    .accessibilityLabel("Next week")
            }
            .padding(.horizontal, 24).padding(.vertical, 14)
            Picker("Schedule", selection: $page) {
                ForEach(SchedulePage.allCases, id: \.self) { item in Text(item.rawValue).tag(item) }
            }
            .pickerStyle(.segmented).padding(.horizontal, 16).padding(.bottom, 10)
            if loading && snapshot == nil {
                Spacer()
                ProgressView("Loading shifts…")
                Spacer()
            } else if let error {
                ContentUnavailableView {
                    Label("Couldn’t load shifts", systemImage: "wifi.exclamationmark")
                } description: { Text(error) } actions: {
                    Button("Try again") { Task { await reload() } }
                }
            } else if displayed.isEmpty && (page == .team || openShifts.isEmpty) {
                ContentUnavailableView("No shifts this week", systemImage: "calendar", description: Text("Try another week or view the team schedule."))
            } else {
                List {
                    Section(page.rawValue) {
                        ForEach(displayed) { shift in
                            Button { selectedShift = shift } label: {
                                ShiftRow(shift: shift, location: snapshot?.locations[shift.location_id ?? ""])
                            }
                            .listRowBackground(Color.white.opacity(0.8))
                        }
                    }
                    if page == .mine && !openShifts.isEmpty {
                        Section("Open shifts") {
                            ForEach(openShifts) { shift in
                                Button { selectedShift = shift } label: {
                                    ShiftRow(shift: shift, location: snapshot?.locations[shift.location_id ?? ""])
                                }
                                .listRowBackground(Color.white.opacity(0.8))
                            }
                        }
                    }
                }
                .scrollContentBackground(.hidden)
            }
        }
        .navigationTitle("Schedule")
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button("Today") { anchorDay = WallClock.today() }
            }
        }
        .refreshable { await reload() }
        .task(id: week) { await reload() }
        .sheet(item: $selectedShift) { shift in
            NavigationStack {
                ShiftDetailView(
                    shift: shift, location: snapshot?.locations[shift.location_id ?? ""],
                    employeeID: profile.id,
                    mode: openShifts.contains(where: { $0.id == shift.id }) ? .open :
                        ((snapshot?.mine.contains(where: { $0.id == shift.id }) ?? false) ? .mine : .team),
                    onChanged: { await reload() }
                )
            }
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
            snapshot = loaded
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
}

private struct ShiftRow: View {
    let shift: ScheduleShift
    let location: String?

    var body: some View {
        HStack(spacing: 16) {
            VStack(spacing: 2) {
                Text(WallClock.label(shift.starts_at, format: "EEE").uppercased())
                    .font(.caption2.bold()).foregroundStyle(.secondary)
                Text(WallClock.label(shift.starts_at, format: "d"))
                    .font(.title2.bold())
            }.frame(width: 38)
            VStack(alignment: .leading, spacing: 5) {
                Text(shift.title).font(.headline)
                Text("\(WallClock.label(shift.starts_at, format: "h:mm a")) – \(WallClock.label(shift.ends_at, format: "h:mm a"))")
                    .font(.subheadline)
                if let location { Text(location).font(.caption).foregroundStyle(.secondary) }
                if shift.has_conflict == true {
                    Label("Conflicts with your schedule", systemImage: "exclamationmark.triangle")
                        .font(.caption).foregroundStyle(.orange)
                }
            }
            Spacer(minLength: 0)
            Image(systemName: "chevron.right").font(.caption).foregroundStyle(.tertiary)
        }
        .padding(.vertical, 9)
        .foregroundStyle(.primary)
    }
}

enum ShiftDetailMode: Equatable { case mine, team, open }

struct ShiftDetailView: View {
    @Environment(\.dismiss) private var dismiss
    let shift: ScheduleShift
    let location: String?
    let employeeID: String
    let mode: ShiftDetailMode
    let onChanged: () async -> Void
    @State private var action: ShiftAction?
    @State private var submitted = false

    private var myAssignment: ShiftAssignment? {
        shift.assignments.first { $0.employee_id == employeeID }
    }

    var body: some View {
        List {
            Section {
                Text(shift.title).font(.title2.bold())
                LabeledContent("Date", value: WallClock.label(shift.starts_at, format: "EEEE, MMMM d"))
                LabeledContent("Time", value: "\(WallClock.label(shift.starts_at, format: "h:mm a")) – \(WallClock.label(shift.ends_at, format: "h:mm a"))")
                if let location { LabeledContent("Location", value: location) }
                if let department = shift.department { LabeledContent("Department", value: department) }
                if let minutes = shift.break_minutes, minutes > 0 {
                    LabeledContent("Break", value: "\(minutes) minutes")
                }
            }
            if let note = myAssignment?.manager_note,
               !note.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                Section("Manager note") { Text(note) }
            }
            if let breaks = myAssignment?.planned_breaks, !breaks.isEmpty {
                Section("Planned breaks") {
                    ForEach(breaks) { item in
                        LabeledContent(item.kind.capitalized, value: "\(WallClock.clockTime(item.start_local)) · \(item.duration_minutes) min")
                    }
                }
            }
            if let notes = shift.notes, !notes.isEmpty { Section("Shift notes") { Text(notes) } }
            if submitted { Section { Label("Request sent for review", systemImage: "checkmark.circle") } }
            // Once a request is sent the actions go away: a second tap would
            // file a second offer (the server now refuses it, but the button
            // should not invite it).
            if mode == .mine && !submitted {
                Section("Request a change") {
                    Button("Swap shift") { action = .swap }
                    Button("Offer for pickup") { action = .pickup }
                    Button("Request to drop") { action = .drop }
                }
            } else if mode == .open && !submitted {
                Section {
                    Button("Claim open shift") { action = .claim }
                }
            }
        }
        .navigationTitle("Shift details")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar { ToolbarItem(placement: .topBarTrailing) { Button("Done") { dismiss() } } }
        .sheet(item: $action) { selection in
            NavigationStack {
                RequestComposerView(action: selection, shift: shift) {
                    submitted = true
                    Task { await onChanged() }
                }
            }
        }
    }
}
