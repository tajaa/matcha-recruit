import SwiftUI

struct PTOView: View {
    @State private var summary: PTOSummary?
    @State private var error: String?
    @State private var busyID: String?
    @State private var showForm = false

    var body: some View {
        List {
            if let summary {
                Section("Balance") {
                    LabeledContent("Available", value: "\(summary.balance.balance_hours) hours")
                }
                Section("Pending requests") {
                    if summary.pending_requests.isEmpty {
                        Text("No pending time off").foregroundStyle(.secondary)
                    }
                    ForEach(summary.pending_requests) { request in
                        VStack(alignment: .leading, spacing: 6) {
                            Text(request.request_type.capitalized).font(.headline)
                            Text("\(request.start_date) – \(request.end_date) · \(request.hours) hours")
                                .font(.subheadline)
                            Button("Cancel request", role: .destructive) {
                                Task { await cancel(request) }
                            }
                            .disabled(busyID != nil)
                        }
                    }
                }
                Section("Approved this year") {
                    if summary.approved_requests.isEmpty {
                        Text("No approved time off yet").foregroundStyle(.secondary)
                    }
                    ForEach(summary.approved_requests) { request in
                        VStack(alignment: .leading, spacing: 4) {
                            Text(request.request_type.capitalized).font(.headline)
                            Text("\(request.start_date) – \(request.end_date) · \(request.hours) hours")
                                .font(.subheadline).foregroundStyle(.secondary)
                        }
                    }
                }
            } else if error == nil {
                ProgressView("Loading time off…")
            }
            if let error { Section { Text(error).foregroundStyle(.red) } }
        }
        .navigationTitle("Time off")
        .toolbar { ToolbarItem(placement: .topBarTrailing) { Button("Request") { showForm = true } } }
        .refreshable { await load() }
        .task { await load() }
        .sheet(isPresented: $showForm) {
            NavigationStack {
                PTORequestForm { Task { await load() } }
            }
        }
    }

    private func load() async {
        do { summary = try await RequestService.pto(); error = nil }
        catch { self.error = error.localizedDescription }
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

private struct PTORequestForm: View {
    @Environment(\.dismiss) private var dismiss
    let onSaved: () -> Void
    @State private var start = Date()
    @State private var end = Date()
    @State private var hours = "8"
    @State private var reason = ""
    @State private var type = "vacation"
    @State private var saving = false
    @State private var error: String?

    var body: some View {
        Form {
            Section {
                DatePicker("From", selection: $start, in: Date()..., displayedComponents: .date)
                DatePicker("Through", selection: $end, in: start..., displayedComponents: .date)
                TextField("Hours", text: $hours).keyboardType(.decimalPad)
                Picker("Type", selection: $type) {
                    Text("Vacation").tag("vacation")
                    Text("Sick").tag("sick")
                    Text("Personal").tag("personal")
                    Text("Other").tag("other")
                }
            }
            Section("Reason (optional)") {
                TextField("Add a note", text: $reason, axis: .vertical).lineLimit(2...4)
            }
            if let error { Section { Text(error).foregroundStyle(.red) } }
            Section {
                Button("Submit request") { Task { await submit() } }
                    .disabled(saving)
            }
        }
        .navigationTitle("Request time off")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar { ToolbarItem(placement: .topBarTrailing) { Button("Cancel") { dismiss() } } }
    }

    private func submit() async {
        let normalizedHours = hours.trimmingCharacters(in: .whitespacesAndNewlines)
            .replacingOccurrences(of: ",", with: ".")
        guard let amount = Decimal(string: normalizedHours), amount > 0 else {
            error = "Enter a positive number of hours."
            return
        }
        saving = true
        error = nil
        defer { saving = false }
        do {
            try await RequestService.requestPTO(PTORequestBody(
                start_date: DateInput.date(start), end_date: DateInput.date(end),
                hours: normalizedHours, reason: reason.isEmpty ? nil : reason,
                request_type: type
            ))
            onSaved()
            dismiss()
        } catch { self.error = error.localizedDescription }
    }
}
