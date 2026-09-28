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
            if loading {
                Section { HStack { ProgressView(); Text("Loading your availability").foregroundStyle(Palette.inkSoft) } }
                    .listRowBackground(GlassRowBackground())
            }
            if let pending {
                Section {
                    Label {
                        VStack(alignment: .leading, spacing: 4) {
                            Text("A change is with your manager").font(TypeScale.headline)
                            if let effective = pending.availability_effective_on {
                                Text("Asked to start \(DateInput.display(effective, pattern: "EEEE, MMM d"))")
                                    .font(TypeScale.subhead).foregroundStyle(Palette.inkSoft)
                            }
                            Text("Withdraw it in Requests to send a different one.")
                                .font(TypeScale.caption).foregroundStyle(Palette.inkSoft)
                        }
                    } icon: {
                        Image(systemName: "clock.badge.checkmark").foregroundStyle(Palette.amber)
                    }
                }
                .listRowBackground(GlassRowBackground())
            }
            Section {
                Toggle("I can work any time", isOn: $alwaysAvailable.animation(.spring(response: 0.4, dampingFraction: 0.86)))
            } header: {
                Eyebrow("Weekly availability")
            } footer: {
                Text("Turn this off to set the hours you can work each day.").font(TypeScale.caption)
            }
            .listRowBackground(GlassRowBackground())
            if !alwaysAvailable {
                ForEach(0..<7, id: \.self) { weekday in
                    Section {
                        ForEach($windows) { $window in
                            if window.weekday == weekday {
                                HStack {
                                    DatePicker("From", selection: $window.start, displayedComponents: .hourAndMinute)
                                        .labelsHidden()
                                    Text("to").foregroundStyle(Palette.inkSoft)
                                    DatePicker("Until", selection: $window.end, displayedComponents: .hourAndMinute)
                                        .labelsHidden()
                                    Spacer()
                                    Button(role: .destructive) {
                                        withAnimation { windows.removeAll { $0.id == window.id } }
                                    } label: {
                                        Image(systemName: "minus.circle.fill").foregroundStyle(Palette.alert)
                                    }
                                    .buttonStyle(.plain)
                                    .accessibilityLabel("Remove \(days[weekday]) window")
                                }
                            }
                        }
                        if windows.filter({ $0.weekday == weekday }).isEmpty {
                            Text("Not available").font(TypeScale.subhead).foregroundStyle(Palette.inkFaint)
                        }
                        Button {
                            withAnimation {
                                windows.append(AvailabilityDraft(
                                    weekday: weekday,
                                    start: DateInput.timeDate("09:00"),
                                    end: DateInput.timeDate("17:00")
                                ))
                            }
                        } label: {
                            Label("Add hours", systemImage: "plus.circle.fill").font(TypeScale.callout)
                        }
                        .disabled(windows.filter { $0.weekday == weekday }.count >= 6)
                    } header: {
                        Eyebrow(days[weekday])
                    }
                    .listRowBackground(GlassRowBackground())
                }
            }
            Section {
                DatePicker("Starts", selection: $effectiveOn, in: Date()..., displayedComponents: .date)
                TextField("Why the change? (optional)", text: $reason, axis: .vertical).lineLimit(2...4)
            } header: {
                Eyebrow("When it starts")
            }
            .listRowBackground(GlassRowBackground())
            if let error {
                Section { ErrorBanner(message: error) }
                    .listRowBackground(Color.clear).listRowInsets(EdgeInsets())
            }
            Section {
                Button { Task { await submit() } } label: {
                    LoadingLabel(title: "Send to my manager", busy: saving)
                }
                .buttonStyle(PrimaryButtonStyle())
                .disabled(loading || saving || pending != nil)
            }
            .listRowBackground(Color.clear)
            .listRowInsets(EdgeInsets())
        }
        .glassForm()
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
                error = "Add hours for at least one day, or turn on \u{201C}I can work any time.\u{201D}"
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
