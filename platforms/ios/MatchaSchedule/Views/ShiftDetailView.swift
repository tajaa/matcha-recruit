import SwiftUI

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

    private var part: DayPart { DayPart(wallClockISO: shift.starts_at) }

    private var myAssignment: ShiftAssignment? {
        shift.assignments.first { $0.employee_id == employeeID }
    }

    private var crew: [ShiftAssignment] {
        shift.assignments.filter { $0.employee_id != employeeID }
    }

    var body: some View {
        List {
            Section {
                VStack(alignment: .leading, spacing: 6) {
                    Label(part.label, systemImage: part.symbol)
                        .font(.subheadline.weight(.medium))
                        .foregroundStyle(part.color)
                        .labelStyle(TightLabel())
                    Text("\(WallClock.label(shift.starts_at, format: "h:mm a")) – \(WallClock.label(shift.ends_at, format: "h:mm a"))")
                        .font(.title.bold())
                        .monospacedDigit()
                        .minimumScaleFactor(0.6)
                        .lineLimit(1)
                    Text(shift.title).font(.title3).foregroundStyle(Color.secondary)
                    if mode == .open || shift.has_conflict == true {
                        HStack(spacing: 6) {
                            if mode == .open { StatusPill(text: "Open", color: .accentColor) }
                            if shift.has_conflict == true { StatusPill(text: "Overlaps your shift", color: .orange) }
                        }
                        .padding(.top, 2)
                    }
                }
                .padding(.vertical, 4)
            }

            Section {
                LabeledContent("Date", value: WallClock.label(shift.starts_at, format: "EEEE, MMMM d"))
                if let duration = WallClock.duration(from: shift.starts_at, to: shift.ends_at) {
                    LabeledContent("Length", value: duration)
                }
                if let location { LabeledContent("Location", value: location) }
                if let department = shift.department, !department.isEmpty {
                    LabeledContent("Department", value: department)
                }
            }

            breaks

            if let note = myAssignment?.manager_note,
               !note.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                Section("From your manager") { Text(note) }
            }
            if let notes = shift.notes, !notes.isEmpty {
                Section("Shift notes") { Text(notes) }
            }
            if !crew.isEmpty {
                Section(mode == .mine ? "Working with you" : "On this shift") {
                    ForEach(crew) { person in
                        HStack(spacing: 12) {
                            Avatar(name: person.name, size: 32)
                            Text(person.name)
                        }
                    }
                }
            }

            actions
        }
        .navigationTitle("Shift")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button("Done") { dismiss() }
            }
        }
        .sheet(item: $action) { selection in
            NavigationStack {
                RequestComposerView(action: selection, shift: shift) {
                    withAnimation { submitted = true }
                    Task { await onChanged() }
                }
            }
        }
    }

    /// The employee's own breaks: what the shift entitles them to, then the
    /// times their manager planned.
    @ViewBuilder
    private var breaks: some View {
        let guidance = myAssignment?.compliance_guidance
        let planned = myAssignment?.planned_breaks ?? []
        let minutes = shift.break_minutes ?? 0
        if guidance?.entitlement != nil || guidance?.mealBreakWaived == true || !planned.isEmpty || minutes > 0 {
            Section("Breaks") {
                if let entitlement = guidance?.entitlement {
                    Label(entitlement, systemImage: guidance?.needsAttention == true ? "exclamationmark.triangle" : "info.circle")
                        .font(.subheadline)
                        .foregroundStyle(guidance?.needsAttention == true ? Color.orange : Color.secondary)
                } else if planned.isEmpty && minutes > 0 {
                    LabeledContent("Break", value: "\(minutes) minutes")
                }
                if guidance?.mealBreakWaived == true {
                    Label("Meal-break waiver applies to this shift.", systemImage: "checkmark.circle")
                        .font(.subheadline)
                        .foregroundStyle(Color.secondary)
                }
                ForEach(planned) { item in
                    LabeledContent {
                        Text("\(item.duration_minutes) min")
                    } label: {
                        Label("\(WallClock.clockTime(item.start_local)) · \(item.kind.capitalized)",
                              systemImage: item.kind == "meal" ? "fork.knife" : "cup.and.saucer")
                            .monospacedDigit()
                    }
                }
            }
        }
    }

    @ViewBuilder
    private var actions: some View {
        if submitted {
            Section {
                Label {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Sent to your manager").font(.headline)
                        Text("Track it in Requests.").font(.subheadline).foregroundStyle(Color.secondary)
                    }
                } icon: {
                    Image(systemName: "checkmark.circle.fill").foregroundStyle(Color.accentColor)
                }
            }
            .sensoryFeedback(.success, trigger: submitted)
        } else if mode == .mine {
            Section("Need a change?") {
                Button { action = .swap } label: { Label("Swap with a coworker", systemImage: "arrow.left.arrow.right") }
                Button { action = .pickup } label: { Label("Offer it up", systemImage: "hand.raised") }
                Button(role: .destructive) { action = .drop } label: { Label("Ask to drop", systemImage: "minus.circle") }
            }
        } else if mode == .open {
            Section {
                Button { action = .claim } label: {
                    Label("Claim this shift", systemImage: "plus.circle.fill").frame(maxWidth: .infinity)
                }
                .primaryActionRow()
                .accessibilityIdentifier("shift.claim")
            }
        }
    }
}
