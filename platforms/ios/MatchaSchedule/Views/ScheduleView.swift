import SwiftUI

private enum SchedulePage: String, CaseIterable {
    case mine = "My shifts"
    case team = "Team"
}

struct ScheduleView: View {
    let profile: EmployeeProfile
    @State private var week = WallClock.weekStart(containing: WallClock.today())
    /// Learned from the store on first load; until then Sunday.
    @State private var weekStartWeekday = 0
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
                Button { week = WallClock.move(week, by: -1) } label: { Image(systemName: "chevron.left") }
                    .accessibilityLabel("Previous week")
                Spacer()
                VStack(spacing: 3) {
                    Text("WEEK OF").font(.caption2.bold()).tracking(2).foregroundStyle(.secondary)
                    Text(WallClock.weekLabel(week))
                        .font(.headline)
                }
                Spacer()
                Button { week = WallClock.move(week, by: 1) } label: { Image(systemName: "chevron.right") }
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
                Button("Today") { week = WallClock.weekStart(containing: WallClock.today(), weekStartWeekday: weekStartWeekday) }
            }
        }
        .refreshable { await reload() }
        .task(id: week) { await reload() }
        .sheet(item: $selectedShift) { shift in
            NavigationStack {
                ShiftDetailView(shift: shift, location: snapshot?.locations[shift.location_id ?? ""], employeeID: profile.id)
            }
        }
    }

    private func reload() async {
        loading = true
        error = nil
        do {
            let loaded = try await ScheduleService.load(week: week)
            snapshot = loaded
            if loaded.weekStartWeekday != weekStartWeekday {
                // A Monday-start store: realign the page so a week is not
                // split across two screens. Changing `week` re-runs the task.
                weekStartWeekday = loaded.weekStartWeekday
                week = WallClock.weekStart(containing: week, weekStartWeekday: loaded.weekStartWeekday)
            }
        }
        catch { self.error = error.localizedDescription }
        loading = false
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

struct ShiftDetailView: View {
    @Environment(\.dismiss) private var dismiss
    let shift: ScheduleShift
    let location: String?
    let employeeID: String

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
               myAssignment?.manager_note_visible_to_employee == true,
               !note.isEmpty {
                Section("Manager note") { Text(note) }
            }
            if let breaks = myAssignment?.planned_breaks, !breaks.isEmpty {
                Section("Planned breaks") {
                    ForEach(breaks) { item in
                        LabeledContent(item.kind.capitalized, value: "\(item.start_local) · \(item.duration_minutes) min")
                    }
                }
            }
            if let notes = shift.notes, !notes.isEmpty { Section("Shift notes") { Text(notes) } }
        }
        .navigationTitle("Shift details")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar { ToolbarItem(placement: .topBarTrailing) { Button("Done") { dismiss() } } }
    }
}
