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
            // No glass here: the sheet is already glass, and glass cannot sit on glass.
            Group {
                VStack(alignment: .leading, spacing: 6) {
                    Label(part.label, systemImage: part.symbol)
                        .font(.app(.subheadline, .medium))
                        .foregroundStyle(part.color)
                        .labelStyle(TightLabel())
                    Text("\(WallClock.label(shift.starts_at, format: "h:mm a")) – \(WallClock.label(shift.ends_at, format: "h:mm a"))")
                        .font(.app(.title, .bold))
                        .monospacedDigit()
                        .minimumScaleFactor(0.6)
                        .lineLimit(1)
                    Text(shift.title).font(.app(.title3)).foregroundStyle(Color.secondary)
                    if mode == .open || shift.has_conflict == true {
                        HStack(spacing: 6) {
                            if mode == .open { StatusPill(text: "Open", color: .brand) }
                            if shift.has_conflict == true { StatusPill(text: "Overlaps your shift", color: .orange) }
                        }
                        .padding(.top, 2)
                    }
                }
            }
            .padding(.horizontal, 4)
            .bareRow(top: 8, bottom: 10)

            VStack(spacing: 12) {
                LabeledContent("Date", value: WallClock.label(shift.starts_at, format: "EEEE, MMMM d"))
                if let duration = WallClock.duration(from: shift.starts_at, to: shift.ends_at) {
                    LabeledContent("Length", value: duration)
                }
                if let location { LabeledContent("Location", value: location) }
                if let department = shift.department, !department.isEmpty {
                    LabeledContent("Department", value: department)
                }
            }
            .cardRow()

            breaks

            if let note = myAssignment?.manager_note,
               !note.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                SectionLabel("From your manager")
                Text(note).frame(maxWidth: .infinity, alignment: .leading).cardRow()
            }
            if let notes = shift.notes, !notes.isEmpty {
                SectionLabel("Shift notes")
                Text(notes).frame(maxWidth: .infinity, alignment: .leading).cardRow()
            }
            if !crew.isEmpty {
                SectionLabel(mode == .mine ? "Working with you" : "On this shift")
                VStack(alignment: .leading, spacing: 12) {
                    ForEach(crew) { person in
                        HStack(spacing: 12) {
                            Avatar(name: person.name, size: 32)
                            Text(person.name)
                            Spacer(minLength: 0)
                        }
                    }
                }
                .cardRow()
            }

            actions
        }
        .listStyle(.plain)
        // Cleared so the sheet's own glass shows behind the cards.
        .scrollContentBackground(.hidden)
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
            SectionLabel("Breaks")
            VStack(alignment: .leading, spacing: 12) {
                if let entitlement = guidance?.entitlement {
                    Label(entitlement, systemImage: guidance?.needsAttention == true ? "exclamationmark.triangle" : "info.circle")
                        .font(.app(.subheadline))
                        .foregroundStyle(guidance?.needsAttention == true ? Color.orange : Color.secondary)
                } else if planned.isEmpty && minutes > 0 {
                    LabeledContent("Break", value: "\(minutes) minutes")
                }
                if guidance?.mealBreakWaived == true {
                    Label("Meal-break waiver applies to this shift.", systemImage: "checkmark.circle")
                        .font(.app(.subheadline))
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
            .frame(maxWidth: .infinity, alignment: .leading)
            .cardRow()
        }
    }

    @ViewBuilder
    private var actions: some View {
        if submitted {
            Label {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Sent to your manager").font(.app(.headline))
                    Text("Track it in Requests.").font(.app(.subheadline)).foregroundStyle(Color.secondary)
                }
            } icon: {
                Image(systemName: "checkmark.circle.fill").foregroundStyle(Color.brand)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .cardRow()
            .sensoryFeedback(.success, trigger: submitted)
        } else if mode == .mine {
            SectionLabel("Need a change?")
            HStack(spacing: 10) {
                change("Swap", symbol: "arrow.left.arrow.right") { action = .swap }
                change("Offer up", symbol: "hand.raised") { action = .pickup }
                change("Drop", symbol: "minus.circle") { action = .drop }
            }
            .bareRow(top: 6, bottom: 16)
        } else if mode == .open {
            Button { action = .claim } label: {
                LoadingLabel(title: "Claim this shift", busy: false)
                    .font(.app(.headline))
                    .padding(.vertical, 6)
            }
            .prominentGlassButton()
            .controlSize(.large)
            .buttonBorderShape(.capsule)
            .bareRow(top: 12, bottom: 16)
            .accessibilityIdentifier("shift.claim")
        }
    }

    private func change(_ title: String, symbol: String, perform: @escaping () -> Void) -> some View {
        Button(action: perform) {
            VStack(spacing: 6) {
                Image(systemName: symbol).font(.title3)
                Text(title).font(.app(.subheadline, .medium))
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, 6)
        }
        .glassButton()
        .buttonBorderShape(.roundedRectangle(radius: 18))
    }
}
