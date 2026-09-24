import SwiftUI

struct RequestsView: View {
    let profile: EmployeeProfile
    @State private var requests: [ScheduleRequest] = []
    @State private var offers: [ScheduleRequest] = []
    @State private var loading = false
    @State private var busyID: String?
    @State private var error: String?
    @State private var showUnavailable = false

    var body: some View {
        List {
            Section("Create") {
                Button("Unavailable dates") { showUnavailable = true }
                NavigationLink("Weekly availability") {
                    AvailabilityView { Task { await load() } }
                }
                if profile.enabled_features.time_off {
                    NavigationLink("Time off") { PTOView() }
                }
            }
            if let error { Section { Text(error).foregroundStyle(.red) } }
            if loading && requests.isEmpty && offers.isEmpty {
                Section { ProgressView("Loading requests…") }
            }
            Section("Incoming offers") {
                if offers.isEmpty { Text("No offers waiting for you").foregroundStyle(.secondary) }
                ForEach(offers) { offer in
                    VStack(alignment: .leading, spacing: 8) {
                        Text("\(offer.employee_name) offered a \(offer.request_type)").font(.headline)
                        if let role = offer.shift_role { Text(role) }
                        if let date = offer.shift_starts_at {
                            Text(WallClock.label(date, format: "EEE, MMM d · h:mm a"))
                                .font(.subheadline).foregroundStyle(.secondary)
                        }
                        Button("Accept offer") { Task { await accept(offer) } }
                            .buttonStyle(.borderedProminent)
                            .disabled(busyID != nil)
                    }
                    .padding(.vertical, 5)
                }
            }
            Section("My requests") {
                if requests.isEmpty { Text("No requests yet").foregroundStyle(.secondary) }
                ForEach(requests) { request in
                    VStack(alignment: .leading, spacing: 8) {
                        HStack {
                            Text(request.title).font(.headline)
                            Spacer()
                            Text(request.status.replacingOccurrences(of: "_", with: " ").capitalized)
                                .font(.caption.bold())
                                .padding(.horizontal, 8).padding(.vertical, 4)
                                .background(.brown.opacity(0.12), in: Capsule())
                        }
                        if let role = request.shift_role { Text(role).font(.subheadline) }
                        if let date = request.shift_starts_at {
                            Text(WallClock.label(date, format: "EEE, MMM d · h:mm a"))
                                .font(.subheadline).foregroundStyle(.secondary)
                        } else if let from = request.unavailable_start {
                            Text("\(from) – \(request.unavailable_end ?? from)")
                                .font(.subheadline).foregroundStyle(.secondary)
                        } else if let effective = request.availability_effective_on {
                            Text("Effective \(effective)").font(.subheadline).foregroundStyle(.secondary)
                        }
                        if let note = request.review_notes, !note.isEmpty {
                            Text(note).font(.footnote).foregroundStyle(.secondary)
                        }
                        if request.isPending && (
                            request.employee_id == profile.id ||
                            (request.status == "awaiting_manager" && request.target_employee_id == profile.id)
                        ) {
                            Button(request.status == "pending" ? "Cancel" : "Withdraw") {
                                Task { await end(request) }
                            }
                            .font(.subheadline)
                            .disabled(busyID != nil)
                        }
                    }
                    .padding(.vertical, 5)
                }
            }
        }
        .navigationTitle("Requests")
        .refreshable { await load() }
        .task { await load() }
        .sheet(isPresented: $showUnavailable) {
            NavigationStack {
                UnavailableView {
                    Task { await load() }
                }
            }
        }
    }

    private func load() async {
        loading = true
        error = nil
        do {
            async let own = RequestService.requests()
            async let incoming = RequestService.offers()
            (requests, offers) = try await (own, incoming)
        } catch { self.error = error.localizedDescription }
        loading = false
    }

    private func accept(_ offer: ScheduleRequest) async {
        busyID = offer.id
        defer { busyID = nil }
        do {
            try await RequestService.accept(offer)
            await load()
        } catch { self.error = error.localizedDescription }
    }

    private func end(_ request: ScheduleRequest) async {
        busyID = request.id
        defer { busyID = nil }
        do {
            if request.status == "pending" {
                try await RequestService.cancel(request)
            } else {
                try await RequestService.withdraw(request)
            }
            await load()
        } catch { self.error = error.localizedDescription }
    }
}

private struct UnavailableView: View {
    @Environment(\.dismiss) private var dismiss
    let onSaved: () -> Void
    @State private var start = Date()
    @State private var end = Date()
    @State private var reason = ""
    @State private var saving = false
    @State private var error: String?

    var body: some View {
        Form {
            Section {
                DatePicker("From", selection: $start, in: Date()..., displayedComponents: .date)
                DatePicker("Through", selection: $end, in: start..., displayedComponents: .date)
            }
            Section("Reason (optional)") {
                TextField("Tell your manager why", text: $reason, axis: .vertical).lineLimit(2...5)
            }
            if let error { Section { Text(error).foregroundStyle(.red) } }
            Section {
                Button("Send for review") {
                    saving = true
                    error = nil
                    Task {
                        defer { saving = false }
                        do {
                            try await RequestService.create(ScheduleRequestBody(
                                request_type: "unavailable", shift_id: nil,
                                target_employee_id: nil, counter_shift_id: nil,
                                unavailable_start: DateInput.date(start),
                                unavailable_end: DateInput.date(end),
                                reason: reason.isEmpty ? nil : reason
                            ))
                            onSaved()
                            dismiss()
                        } catch { self.error = error.localizedDescription }
                    }
                }
                .disabled(saving || DateInput.date(end) < DateInput.date(start))
            }
        }
        .navigationTitle("Unavailable dates")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar { ToolbarItem(placement: .topBarTrailing) { Button("Cancel") { dismiss() } } }
    }
}
