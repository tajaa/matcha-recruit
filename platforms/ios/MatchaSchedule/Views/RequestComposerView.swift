import SwiftUI

enum ShiftAction: String, Identifiable {
    case swap, pickup, drop, claim
    var id: String { rawValue }
    var title: String {
        switch self {
        case .swap: "Swap shift"
        case .pickup: "Offer up shift"
        case .drop: "Drop shift"
        case .claim: "Claim open shift"
        }
    }

    /// What happens after sending, in one line.
    var explainer: String {
        switch self {
        case .swap: "Your coworker accepts first, then your manager approves the trade."
        case .pickup: "Anyone at your store can take it; your manager approves who does."
        case .drop: "Your manager decides whether the shift can go uncovered."
        case .claim: "Your manager approves the claim before it's yours."
        }
    }

    var submitTitle: String {
        switch self {
        case .swap: "Send swap request"
        case .pickup: "Offer it up"
        case .drop: "Ask to drop"
        case .claim: "Claim shift"
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
            Section {
                ShiftCard(shift: shift, location: nil, isOpen: action == .claim)
            } footer: {
                Text(action.explainer).font(TypeScale.caption).padding(.top, 6)
            }
            .listRowBackground(Color.clear)
            .listRowInsets(EdgeInsets())

            if action == .swap {
                Section {
                    if loading {
                        HStack { ProgressView(); Text("Loading coworkers").foregroundStyle(Palette.inkSoft) }
                    }
                    Picker("Coworker", selection: $targetEmployeeID) {
                        Text("Choose").tag("")
                        ForEach(coworkers) { person in Text(person.name).tag(person.id) }
                    }
                    .onChange(of: targetEmployeeID) { _, _ in counterShiftID = "" }
                    Picker("Their shift", selection: $counterShiftID) {
                        Text("Choose").tag("")
                        ForEach(counterShifts) { candidate in
                            Text("\(candidate.title) · \(WallClock.label(candidate.starts_at, format: "EEE MMM d, h:mm a"))")
                                .tag(candidate.id)
                        }
                    }
                    .disabled(targetEmployeeID.isEmpty)
                    if !targetEmployeeID.isEmpty && counterShifts.isEmpty && !loading {
                        Text("They have no published shifts in the next four weeks.")
                            .font(TypeScale.caption).foregroundStyle(Palette.inkSoft)
                    }
                } header: {
                    Eyebrow("Trade with")
                }
                .listRowBackground(GlassRowBackground())
            }
            if action == .claim && shift.has_conflict == true {
                Section {
                    Label("This overlaps one of your shifts. Your manager will see that.", systemImage: "exclamationmark.triangle.fill")
                        .font(TypeScale.subhead)
                        .foregroundStyle(Palette.amber)
                }
                .listRowBackground(GlassRowBackground())
            }
            Section {
                TextField("Add context (optional)", text: $reason, axis: .vertical)
                    .lineLimit(2...5)
            } header: {
                Eyebrow("Note for your manager")
            }
            .listRowBackground(GlassRowBackground())
            if let error {
                Section { ErrorBanner(message: error) }
                    .listRowBackground(Color.clear).listRowInsets(EdgeInsets())
            }
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
                } label: {
                    LoadingLabel(title: action.submitTitle, busy: saving)
                }
                .buttonStyle(PrimaryButtonStyle())
                .disabled(saving || loading || (action == .swap && (targetEmployeeID.isEmpty || counterShiftID.isEmpty)))
            }
            .listRowBackground(Color.clear)
            .listRowInsets(EdgeInsets())
        }
        .glassForm(DayPart(wallClockISO: shift.starts_at))
        .navigationTitle(action.title)
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button { dismiss() } label: { Text("Cancel").font(TypeScale.callout) }
            }
        }
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
