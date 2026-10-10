import SwiftUI

/// Create a shift or change one: the job, the day, the hours and how many
/// people it needs. The server sets the legally required break.
struct ShiftEditorView: View {
    enum Mode {
        /// A new shift on this calendar day ("2026-10-12").
        case create(day: String)
        case edit(ScheduleShift)
    }

    @Environment(\.dismiss) private var dismiss
    let mode: Mode
    let location: ManagedLocation
    let jobs: [ScheduleJob]
    let onSaved: () async -> Void
    @State private var jobID: String
    @State private var day: Date
    @State private var start: Date
    @State private var end: Date
    @State private var requiredStaff: Int
    @State private var notes: String
    @State private var saving = false
    @State private var error: String?
    @State private var force: ForcePrompt?

    init(mode: Mode, location: ManagedLocation, jobs: [ScheduleJob], onSaved: @escaping () async -> Void) {
        self.mode = mode
        self.location = location
        self.jobs = jobs
        self.onSaved = onSaved
        switch mode {
        case .create(let dayKey):
            let date = WallClock.date("\(dayKey)T00:00:00Z") ?? Date()
            _jobID = State(initialValue: jobs.count == 1 ? jobs[0].id : "")
            _day = State(initialValue: date)
            _start = State(initialValue: WallClock.combine(day: date, time: WallClock.date("\(dayKey)T09:00:00Z") ?? date))
            _end = State(initialValue: WallClock.combine(day: date, time: WallClock.date("\(dayKey)T17:00:00Z") ?? date))
            _requiredStaff = State(initialValue: 1)
            _notes = State(initialValue: "")
        case .edit(let shift):
            let starts = WallClock.date(shift.starts_at) ?? Date()
            _jobID = State(initialValue: shift.job_id ?? "")
            _day = State(initialValue: starts)
            _start = State(initialValue: starts)
            _end = State(initialValue: WallClock.date(shift.ends_at) ?? starts)
            _requiredStaff = State(initialValue: shift.required_staff ?? max(1, shift.assignments.count))
            _notes = State(initialValue: shift.notes ?? "")
        }
    }

    private var editing: ScheduleShift? {
        if case .edit(let shift) = mode { return shift }
        return nil
    }

    private var window: (start: Date, end: Date) { WallClock.window(day: day, start: start, end: end) }
    private var overnight: Bool { WallClock.dayKey(window.end) != WallClock.dayKey(window.start) }

    var body: some View {
        Form {
            if jobs.isEmpty {
                Section {
                    Text("\(location.displayName) has no jobs yet. Add one on the web, then come back.")
                        .foregroundStyle(Color.secondary)
                }
            } else {
                Section {
                    Picker("Job", selection: $jobID) {
                        if jobID.isEmpty { Text("Choose a job").tag("") }
                        ForEach(jobs) { Text($0.name).tag($0.id) }
                    }
                    .accessibilityIdentifier("editor.job")
                }
            }

            Section {
                DatePicker("Day", selection: $day, displayedComponents: .date)
                DatePicker("Starts", selection: $start, displayedComponents: .hourAndMinute)
                DatePicker("Ends", selection: $end, displayedComponents: .hourAndMinute)
            } footer: {
                if overnight {
                    Text("Ends the next day, \(WallClock.format(window.end, "EEEE")).")
                }
            }

            Section {
                Stepper("People needed: \(requiredStaff)", value: $requiredStaff, in: 1...99)
                TextField("Notes for the crew (optional)", text: $notes, axis: .vertical).lineLimit(2...5)
            } footer: {
                Text(editing?.status == "published"
                     ? "This shift is published. Your crew sees the change right away."
                     : "Saved as a draft. Your crew sees it once you publish the week.")
            }

            if let error {
                Section { ErrorRow(message: error) }
            }

            Section {
                Button { Task { await save() } } label: {
                    LoadingLabel(title: editing == nil ? "Add shift" : "Save changes", busy: saving)
                }
                .primaryActionRow()
                .disabled(saving || jobID.isEmpty)
                .accessibilityIdentifier("editor.save")
            }
        }
        // Shift times are the store's clock face, stored as UTC: pick on that calendar.
        .environment(\.timeZone, WallClock.timeZone)
        .appBackdrop()
        .navigationTitle(editing == nil ? "New shift" : "Edit shift")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarLeading) { Button("Cancel") { dismiss() } }
        }
        .forcePrompt($force) { message in error = message }
    }

    private func save() async {
        saving = true
        error = nil
        defer { saving = false }
        let (from, until) = window
        let note = notes.trimmingCharacters(in: .whitespacesAndNewlines)
        let write: (Bool) async throws -> Void
        if let shift = editing {
            var patch = ShiftPatch()
            let startsAt = WallClock.iso(from), endsAt = WallClock.iso(until)
            if startsAt != shift.starts_at.replacingOccurrences(of: "+00:00", with: "Z")
                || endsAt != shift.ends_at.replacingOccurrences(of: "+00:00", with: "Z") {
                patch.starts_at = startsAt
                patch.ends_at = endsAt
                // New hours can owe a different break: let the server set it.
                patch.break_mode = "auto"
            }
            if jobID != shift.job_id { patch.job_id = jobID }
            if requiredStaff != shift.required_staff { patch.required_staff = requiredStaff }
            if note != (shift.notes ?? "") { patch.notes = .some(note.isEmpty ? nil : note) }
            let shiftID = shift.id
            write = { force in try await ManagerService.updateShift(shiftID, patch, force: force) }
        } else {
            let body = ShiftCreateBody(
                job_id: jobID, starts_at: WallClock.iso(from), ends_at: WallClock.iso(until),
                location_id: location.id, required_staff: requiredStaff, notes: note.isEmpty ? nil : note
            )
            write = { force in try await ManagerService.createShift(body, force: force) }
        }
        do {
            try await ForcePrompt.run($force) { force in
                try await write(force)
                await onSaved()
                dismiss()
            }
        } catch {
            self.error = error.localizedDescription
        }
    }
}
