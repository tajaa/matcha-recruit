import SwiftUI

enum ShiftAction: String, Identifiable {
    case swap, pickup, drop, claim
    var id: String { rawValue }
    var title: String {
        switch self {
        case .swap: "Swap shift"
        case .pickup: "Offer for pickup"
        case .drop: "Request to drop"
        case .claim: "Claim open shift"
        }
    }
}

struct RequestComposerView: View {
    @Environment(\.dismiss) private var dismiss
    let action: ShiftAction
    let shift: ScheduleShift
    let onSaved: () -> Void

    @State private var reason = ""
    @State private var coworkers: [Coworker] = []
    @State private var teamShifts: [ScheduleShift] = []
    @State private var targetEmployeeID = ""
    @State private var counterShiftID = ""
    @State private var loading = false
    @State private var saving = false
    @State private var error: String?

    private var counterShifts: [ScheduleShift] {
        teamShifts.filter { shift in
            shift.id != self.shift.id &&
            shift.assignments.contains { $0.employee_id == targetEmployeeID }
        }.sorted { $0.starts_at < $1.starts_at }
    }

    var body: some View {
        Form {
            Section("Shift") {
                Text(shift.title)
                Text("\(WallClock.label(shift.starts_at, format: "EEE, MMM d · h:mm a")) – \(WallClock.label(shift.ends_at, format: "h:mm a"))")
                    .foregroundStyle(.secondary)
            }
            if action == .swap {
                Section("Swap with") {
                    if loading { ProgressView("Loading coworkers…") }
                    Picker("Coworker", selection: $targetEmployeeID) {
                        Text("Select a coworker").tag("")
                        ForEach(coworkers) { person in Text(person.name).tag(person.id) }
                    }
                    .onChange(of: targetEmployeeID) { _, _ in counterShiftID = "" }
                    Picker("Their shift", selection: $counterShiftID) {
                        Text("Select a shift").tag("")
                        ForEach(counterShifts) { candidate in
                            Text("\(candidate.title) · \(WallClock.label(candidate.starts_at, format: "MMM d, h:mm a"))")
                                .tag(candidate.id)
                        }
                    }
                    if !targetEmployeeID.isEmpty && counterShifts.isEmpty && !loading {
                        Text("No published shifts are available for this coworker in the next four weeks.")
                            .font(.footnote).foregroundStyle(.secondary)
                    }
                }
            }
            if action == .claim && shift.has_conflict == true {
                Section { Label("This shift overlaps one of yours. A manager will review the claim.", systemImage: "exclamationmark.triangle") }
            }
            Section("Reason (optional)") {
                TextField("Add a note for your manager", text: $reason, axis: .vertical)
                    .lineLimit(2...5)
            }
            if let error { Section { Text(error).foregroundStyle(.red) } }
            Section {
                Button {
                    saving = true
                    error = nil
                    Task {
                        defer { saving = false }
                        do {
                            try await RequestService.create(ScheduleRequestBody(
                                request_type: action.rawValue, shift_id: shift.id,
                                target_employee_id: action == .swap ? targetEmployeeID : nil,
                                counter_shift_id: action == .swap ? counterShiftID : nil,
                                unavailable_start: nil, unavailable_end: nil,
                                reason: reason.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? nil : reason
                            ))
                            onSaved()
                            dismiss()
                        } catch { self.error = error.localizedDescription }
                    }
                } label: { Text(action.title).frame(maxWidth: .infinity) }
                    .disabled(saving || loading || (action == .swap && (targetEmployeeID.isEmpty || counterShiftID.isEmpty)))
            }
        }
        .navigationTitle(action.title)
        .navigationBarTitleDisplayMode(.inline)
        .toolbar { ToolbarItem(placement: .topBarTrailing) { Button("Cancel") { dismiss() } } }
        .task {
            guard action == .swap else { return }
            loading = true
            defer { loading = false }
            do {
                async let people = RequestService.coworkers()
                let start = WallClock.weekStart(containing: WallClock.today())
                let end = WallClock.move(start, by: 4)
                async let shifts = ScheduleService.teamShifts(from: start, through: end)
                (coworkers, teamShifts) = try await (people, shifts)
            } catch { self.error = error.localizedDescription }
        }
    }
}
