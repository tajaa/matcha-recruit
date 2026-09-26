import SwiftUI

private struct AvailabilityDraft: Identifiable {
    let id = UUID()
    let weekday: Int
    var start: Date
    var end: Date
}

struct AvailabilityView: View {
    @Environment(\.dismiss) private var dismiss
    let onSaved: () -> Void

    @State private var alwaysAvailable = true
    @State private var windows: [AvailabilityDraft] = []
    @State private var effectiveOn = Date()
    @State private var reason = ""
    @State private var pending: ScheduleRequest?
    @State private var loading = true
    @State private var saving = false
    @State private var error: String?

    private let days = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]

    var body: some View {
        Form {
            if loading { ProgressView("Loading availability…") }
            if let pending {
                Section {
                    Label("A change is awaiting manager review", systemImage: "clock")
                    if let effective = pending.availability_effective_on {
                        Text("Requested start: \(effective)")
                    }
                    Text("Withdraw that request in Requests before submitting another.")
                        .font(.footnote).foregroundStyle(.secondary)
                }
            }
            Section {
                Toggle("Always available", isOn: $alwaysAvailable)
            } footer: {
                Text("Choose times for each day if your availability varies during the week.")
            }
            if !alwaysAvailable {
                ForEach(0..<7, id: \.self) { weekday in
                    Section(days[weekday]) {
                        ForEach($windows) { $window in
                            if window.weekday == weekday {
                                VStack(alignment: .leading) {
                                    DatePicker("From", selection: $window.start, displayedComponents: .hourAndMinute)
                                    DatePicker("Until", selection: $window.end, displayedComponents: .hourAndMinute)
                                    Button("Remove window", role: .destructive) {
                                        windows.removeAll { $0.id == window.id }
                                    }
                                    .font(.footnote)
                                }
                            }
                        }
                        Button("Add time window") {
                            windows.append(AvailabilityDraft(
                                weekday: weekday,
                                start: DateInput.timeDate("09:00"),
                                end: DateInput.timeDate("17:00")
                            ))
                        }
                        .disabled(windows.filter { $0.weekday == weekday }.count >= 6)
                    }
                }
            }
            Section("When this should start") {
                DatePicker("Effective date", selection: $effectiveOn, in: Date()..., displayedComponents: .date)
                TextField("Reason (optional)", text: $reason, axis: .vertical).lineLimit(2...4)
            }
            if let error { Section { Text(error).foregroundStyle(.red) } }
            Section {
                Button("Send for review") { Task { await submit() } }
                    .disabled(loading || saving || pending != nil)
            }
        }
        .navigationTitle("Availability")
        .navigationBarTitleDisplayMode(.inline)
        .task { await load() }
    }

    private func load() async {
        loading = true
        defer { loading = false }
        do {
            let current = try await RequestService.availability()
            alwaysAvailable = current.availability_state != "windows"
            windows = current.windows.map {
                AvailabilityDraft(weekday: $0.weekday,
                                  start: DateInput.timeDate($0.start_time),
                                  end: DateInput.timeDate($0.end_time))
            }
            pending = current.pending_request
        } catch { self.error = error.localizedDescription }
    }

    private func submit() async {
        error = nil
        let payload: [AvailabilityWindow]
        if alwaysAvailable {
            payload = []
        } else {
            guard !windows.isEmpty else {
                error = "Add at least one time window, or choose Always available."
                return
            }
            guard windows.allSatisfy({ DateInput.time($0.end) > DateInput.time($0.start) }) else {
                error = "Each end time must be after its start time."
                return
            }
            payload = windows.map {
                AvailabilityWindow(weekday: $0.weekday,
                                   start_time: DateInput.time($0.start),
                                   end_time: DateInput.time($0.end))
            }
        }
        saving = true
        defer { saving = false }
        do {
            try await RequestService.requestAvailability(AvailabilityChangeBody(
                availability: AvailabilityReplaceBody(
                    availability_state: alwaysAvailable ? "always_available" : "windows",
                    windows: payload
                ),
                effective_on: DateInput.date(effectiveOn),
                reason: reason.isEmpty ? nil : reason
            ))
            onSaved()
            dismiss()
        } catch { self.error = error.localizedDescription }
    }
}
