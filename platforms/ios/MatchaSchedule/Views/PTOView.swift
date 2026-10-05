import SwiftUI

struct PTOView: View {
    @State private var summary: PTOSummary?
    @State private var error: String?
    @State private var busyID: String?
    @State private var showForm = false

    var body: some View {
        List {
            if let error {
                Section { ErrorRow(message: error) { Task { await load() } } }
            }
            if let summary {
                Section {
                    LabeledContent("Available") {
                        Text("\(Self.trimmed(summary.balance.balance_hours)) hours")
                            .font(.title2.bold())
                            .monospacedDigit()
                            .foregroundStyle(Color.primary)
                            .contentTransition(.numericText())
                    }
                    Button { showForm = true } label: { Label("Request time off", systemImage: "plus") }
                }
                Section("Waiting for approval") {
                    if summary.pending_requests.isEmpty {
                        Text("Nothing pending.").foregroundStyle(Color.secondary)
                    }
                    ForEach(summary.pending_requests) { request in
                        PTORow(request: request, pending: true, busy: busyID == request.id,
                               disabled: busyID != nil) { Task { await cancel(request) } }
                    }
                }
                Section("Approved this year") {
                    if summary.approved_requests.isEmpty {
                        Text("No approved time off yet this year.").foregroundStyle(Color.secondary)
                    }
                    ForEach(summary.approved_requests) { request in
                        PTORow(request: request, pending: false, busy: false, disabled: true) {}
                    }
                }
            } else if error == nil {
                Section { HStack { ProgressView(); Text("Loading your time off").foregroundStyle(Color.secondary) } }
            }
        }
        .navigationTitle("Time off")
        .navigationBarTitleDisplayMode(.inline)
        .refreshable { await load() }
        .task { await load() }
        .sheet(isPresented: $showForm) {
            NavigationStack {
                PTORequestForm { Task { await load() } }
            }
        }
    }

    /// "40.00" → "40", "7.50" → "7.5".
    static func trimmed(_ hours: String) -> String {
        guard hours.contains(".") else { return hours }
        var value = hours
        while value.hasSuffix("0") { value.removeLast() }
        if value.hasSuffix(".") { value.removeLast() }
        return value
    }

    private func load() async {
        do { summary = try await RequestService.pto(); error = nil }
        catch { if !error.isCancellation { self.error = error.localizedDescription } }
    }

    private func cancel(_ request: PTORequest) async {
        busyID = request.id
        defer { busyID = nil }
        do {
            try await RequestService.cancelPTO(request.id)
            await load()
        } catch { self.error = error.localizedDescription }
    }
}

private struct PTORow: View {
    let request: PTORequest
    let pending: Bool
    let busy: Bool
    let disabled: Bool
    let onCancel: () -> Void

    var body: some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 3) {
                Label(request.request_type.capitalized,
                      systemImage: request.request_type == "sick" ? "cross.case" : "sun.max")
                    .font(.headline)
                    .labelStyle(TightLabel())
                Text(range + " · \(PTOView.trimmed(request.hours)) h")
                    .font(.subheadline).foregroundStyle(Color.secondary).monospacedDigit()
            }
            Spacer()
            if pending {
                Button(role: .destructive, action: onCancel) {
                    if busy { ProgressView() } else { Text("Cancel") }
                }
                .buttonStyle(.borderless)
                .disabled(disabled)
            }
        }
    }

    private var range: String {
        request.start_date == request.end_date
            ? DateInput.display(request.start_date, pattern: "EEE, MMM d")
            : "\(DateInput.display(request.start_date)) – \(DateInput.display(request.end_date))"
    }
}

private struct PTORequestForm: View {
    @Environment(\.dismiss) private var dismiss
    @Environment(AppState.self) private var appState
    let onSaved: () -> Void
    @State private var start = Date()
    @State private var end = Date()
    @State private var hours = "8"
    @State private var reason = ""
    @State private var type = "vacation"
    @State private var saving = false
    @State private var error: String?

    private var zone: TimeZone { appState.storeTimeZone ?? .current }

    var body: some View {
        Form {
            Section {
                Picker("Kind", selection: $type) {
                    Text("Vacation").tag("vacation")
                    Text("Sick").tag("sick")
                    Text("Personal").tag("personal")
                    Text("Other").tag("other")
                }
            }
            Section {
                DatePicker("From", selection: $start, in: Date()..., displayedComponents: .date)
                DatePicker("Through", selection: $end, in: start..., displayedComponents: .date)
                HStack {
                    Text("Hours")
                    Spacer()
                    TextField("8", text: $hours)
                        .keyboardType(.decimalPad)
                        .multilineTextAlignment(.trailing)
                        .frame(width: 80)
                }
            } header: {
                Text("Dates")
            }
            Section {
                TextField("Add a note (optional)", text: $reason, axis: .vertical).lineLimit(2...4)
            } header: {
                Text("Note for your manager")
            }
            if let error {
                Section { ErrorRow(message: error) }
            }
            Section {
                Button { Task { await submit() } } label: {
                    LoadingLabel(title: "Send request", busy: saving)
                }
                .primaryActionRow()
                .disabled(saving)
            }
        }
        // The pickers choose days on the store's calendar.
        .environment(\.timeZone, zone)
        .navigationTitle("Request time off")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button("Cancel") { dismiss() }
            }
        }
    }

    private func submit() async {
        let normalizedHours = hours.trimmingCharacters(in: .whitespacesAndNewlines)
            .replacingOccurrences(of: ",", with: ".")
        guard let amount = Decimal(string: normalizedHours), amount > 0 else {
            error = "Enter a number of hours above zero."
            return
        }
        saving = true
        error = nil
        defer { saving = false }
        do {
            try await RequestService.requestPTO(PTORequestBody(
                start_date: DateInput.date(start, timeZone: zone), end_date: DateInput.date(end, timeZone: zone),
                hours: normalizedHours, reason: reason.isEmpty ? nil : reason,
                request_type: type
            ))
            onSaved()
            dismiss()
        } catch { self.error = error.localizedDescription }
    }
}
