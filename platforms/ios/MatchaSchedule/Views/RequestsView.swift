import SwiftUI

struct RequestsView: View {
    let profile: EmployeeProfile
    @State private var requests: [ScheduleRequest] = []
    @State private var offers: [ScheduleRequest] = []
    @State private var loading = false
    @State private var loaded = false
    @State private var busyID: String?
    @State private var error: String?
    @State private var showUnavailable = false
    @State private var showAvailability = false
    @State private var showTimeOff = false

    var body: some View {
        List {
            HStack(spacing: 10) {
                shortcut("Can't work", symbol: "calendar.badge.minus") { showUnavailable = true }
                shortcut("Availability", symbol: "clock.arrow.2.circlepath") { showAvailability = true }
                if profile.enabled_features.time_off {
                    shortcut("Time off", symbol: "sun.horizon") { showTimeOff = true }
                }
            }
            .bareRow(top: 8, bottom: 4)

            if let error {
                ErrorRow(message: error) { Task { await load() } }.cardRow()
            }

            SectionLabel("Waiting on you")
            if !loaded && loading {
                placeholderRow
            } else if offers.isEmpty {
                Text("No offers from coworkers right now.")
                    .foregroundStyle(Color.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .cardRow()
            } else {
                ForEach(offers) { offer in
                    GlassHero {
                        OfferRow(offer: offer, busy: busyID == offer.id, disabled: busyID != nil) {
                            Task { await accept(offer) }
                        }
                    }
                    .bareRow(top: 6, bottom: 6)
                }
            }

            SectionLabel("Your requests")
            if !loaded && loading {
                placeholderRow
                placeholderRow
            } else if requests.isEmpty {
                Text("Swaps, drops and time off you ask for will show up here.")
                    .foregroundStyle(Color.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .cardRow()
            } else {
                ForEach(requests) { request in
                    RequestRow(
                        request: request,
                        canEnd: request.isPending && (
                            request.employee_id == profile.id ||
                            (request.status == "awaiting_manager" && request.target_employee_id == profile.id)
                        ),
                        busy: busyID == request.id,
                        disabled: busyID != nil
                    ) { Task { await end(request) } }
                    .cardRow()
                }
            }
        }
        .listStyle(.plain)
        .appBackdrop()
        .animation(.default, value: offers.map(\.id))
        .animation(.default, value: requests.map(\.id))
        .navigationTitle("Requests")
        .refreshable { await load() }
        .task { await load() }
        .navigationDestination(isPresented: $showAvailability) {
            AvailabilityView { Task { await load() } }
        }
        .navigationDestination(isPresented: $showTimeOff) { PTOView() }
        .sheet(isPresented: $showUnavailable) {
            NavigationStack {
                UnavailableView { Task { await load() } }
            }
        }
    }

    private func shortcut(_ title: String, symbol: String, perform: @escaping () -> Void) -> some View {
        Button(action: perform) {
            VStack(spacing: 6) {
                Image(systemName: symbol).font(.title3)
                Text(title).font(.app(.subheadline, .medium)).lineLimit(1).minimumScaleFactor(0.8)
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, 8)
        }
        .glassButton()
        .buttonBorderShape(.roundedRectangle(radius: 20))
    }

    private var placeholderRow: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text("Shift swap request").font(.app(.headline))
            Text("Monday, Jan 1 · 9:00 AM").font(.app(.subheadline))
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .redacted(reason: .placeholder)
        .cardRow()
        .accessibilityLabel("Loading requests")
    }

    private func load() async {
        loading = true
        error = nil
        do {
            async let own = RequestService.requests()
            async let incoming = RequestService.offers()
            (requests, offers) = try await (own, incoming)
        } catch {
            if !error.isCancellation { self.error = error.localizedDescription }
        }
        loading = false
        loaded = true
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

// MARK: - Vocabulary
//
// The server's states, in the words a crew member uses.

extension ScheduleRequest {
    var kindLabel: String {
        switch request_type {
        case "swap": "Shift swap"
        case "pickup": "Offered up"
        case "drop": "Drop"
        case "claim": "Open shift claim"
        case "unavailable": "Can't work"
        case "availability": "Availability change"
        default: request_type.capitalized
        }
    }

    var kindSymbol: String {
        switch request_type {
        case "swap": "arrow.left.arrow.right"
        case "pickup": "hand.raised.fill"
        case "drop": "minus.circle.fill"
        case "claim": "plus.circle.fill"
        case "unavailable": "calendar.badge.minus"
        case "availability": "clock.arrow.2.circlepath"
        default: "doc.text"
        }
    }

    var statusLabel: String {
        switch status {
        case "pending": "Pending"
        case "awaiting_counterparty": "Waiting on coworker"
        case "awaiting_manager": "With your manager"
        case "approved": "Approved"
        case "denied": "Declined"
        case "cancelled": "Cancelled"
        default: status.replacingOccurrences(of: "_", with: " ").capitalized
        }
    }

    var statusColor: Color {
        switch status {
        case "approved": .brand
        case "denied": .red
        case "awaiting_counterparty": .indigo
        case "pending", "awaiting_manager": .orange
        default: .secondary
        }
    }

    /// When the request is about, in one line.
    var whenLine: String? {
        if let starts = shift_starts_at {
            return WallClock.label(starts, format: "EEE, MMM d · h:mm a")
        }
        if let from = unavailable_start {
            let to = unavailable_end ?? from
            return from == to ? DateInput.display(from) : "\(DateInput.display(from)) – \(DateInput.display(to))"
        }
        if let effective = availability_effective_on {
            return "Starts \(DateInput.display(effective))"
        }
        return nil
    }

    /// The shift a swap asks for in return, once one is chosen.
    var counterShiftLine: String? {
        guard let starts = counter_shift_starts_at else { return nil }
        var line = WallClock.label(starts, format: "EEE, MMM d · h:mm a")
        if let ends = counter_shift_ends_at { line += " – " + WallClock.label(ends, format: "h:mm a") }
        if let role = counter_shift_role, !role.isEmpty { line += " · " + role }
        return line
    }

    /// The shift on offer: when, until when, and as what.
    var offeredShiftLine: String? {
        guard let starts = shift_starts_at else { return nil }
        var line = WallClock.label(starts, format: "EEEE, MMM d · h:mm a")
        if let ends = shift_ends_at { line += " – " + WallClock.label(ends, format: "h:mm a") }
        if let role = shift_role, !role.isEmpty { line += " · " + role }
        return line
    }
}

// MARK: - Rows

private struct OfferRow: View {
    let offer: ScheduleRequest
    let busy: Bool
    let disabled: Bool
    let onAccept: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(offer.request_type == "swap"
                 ? "\(offer.employee_name) wants to swap"
                 : "\(offer.employee_name) is offering a shift")
                .font(.app(.headline))
            if let offered = offer.offeredShiftLine {
                Text(offer.request_type == "swap" ? "Offers: \(offered)" : offered)
                    .font(.app(.subheadline)).foregroundStyle(Color.secondary).monospacedDigit()
            }
            if let wanted = offer.counterShiftLine {
                Text("For: \(wanted)")
                    .font(.app(.subheadline)).foregroundStyle(Color.secondary).monospacedDigit()
            }
            if let reason = offer.reason, !reason.isEmpty {
                Text("\u{201C}\(reason)\u{201D}").font(.app(.subheadline)).foregroundStyle(Color.secondary)
            }
            Button(action: onAccept) {
                LoadingLabel(title: offer.request_type == "swap" ? "Accept swap" : "Take this shift", busy: busy)
            }
            .prominentGlassButton()
            .buttonBorderShape(.capsule)
            .disabled(disabled)
            .padding(.top, 6)
        }
    }
}

private struct RequestRow: View {
    let request: ScheduleRequest
    let canEnd: Bool
    let busy: Bool
    let disabled: Bool
    let onEnd: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .firstTextBaseline) {
                Label(request.kindLabel, systemImage: request.kindSymbol)
                    .font(.app(.headline))
                    .labelStyle(TightLabel())
                Spacer(minLength: 8)
                StatusPill(text: request.statusLabel, color: request.statusColor)
            }
            if let role = request.shift_role {
                Text(role).font(.app(.subheadline)).foregroundStyle(Color.secondary)
            }
            if let when = request.whenLine {
                Text(when).font(.app(.subheadline)).foregroundStyle(Color.secondary).monospacedDigit()
            }
            if let wanted = request.counterShiftLine {
                Text("For: \(wanted)").font(.app(.subheadline)).foregroundStyle(Color.secondary).monospacedDigit()
            }
            if let note = request.review_notes, !note.isEmpty {
                Text("\u{201C}\(note)\u{201D}").font(.app(.subheadline)).foregroundStyle(Color.secondary)
            }
            if canEnd {
                Button(role: .destructive, action: onEnd) {
                    if busy { ProgressView() } else { Text(request.status == "pending" ? "Cancel request" : "Withdraw") }
                }
                .buttonStyle(.borderless)
                .font(.app(.subheadline))
                .disabled(disabled)
                .padding(.top, 2)
            }
        }
        .padding(.vertical, 2)
    }
}

// MARK: - Can't work

private struct UnavailableView: View {
    @Environment(\.dismiss) private var dismiss
    @Environment(AppState.self) private var appState
    let onSaved: () -> Void
    @State private var start = Date()
    @State private var end = Date()
    @State private var reason = ""
    @State private var saving = false
    @State private var error: String?

    private var zone: TimeZone { appState.storeTimeZone ?? .current }

    var body: some View {
        Form {
            Section {
                DatePicker("From", selection: $start, in: Date()..., displayedComponents: .date)
                DatePicker("Through", selection: $end, in: start..., displayedComponents: .date)
            } header: {
                Text("Dates you can't work")
            } footer: {
                Text("Your manager sees this before building the schedule.")
            }
            Section {
                TextField("Why? (optional)", text: $reason, axis: .vertical).lineLimit(2...5)
            } header: {
                Text("Note for your manager")
            }
            if let error {
                Section { ErrorRow(message: error) }
            }
            Section {
                Button {
                    saving = true
                    error = nil
                    Task {
                        defer { saving = false }
                        do {
                            try await RequestService.create(ScheduleRequestBody(
                                request_type: "unavailable", shift_id: nil,
                                target_employee_id: nil, counter_shift_id: nil,
                                unavailable_start: DateInput.date(start, timeZone: zone),
                                unavailable_end: DateInput.date(end, timeZone: zone),
                                reason: reason.isEmpty ? nil : reason
                            ))
                            onSaved()
                            dismiss()
                        } catch { self.error = error.localizedDescription }
                    }
                } label: {
                    LoadingLabel(title: "Send to my manager", busy: saving)
                }
                .primaryActionRow()
                .disabled(saving || DateInput.date(end, timeZone: zone) < DateInput.date(start, timeZone: zone))
            }
        }
        // The pickers choose days on the store's calendar.
        .environment(\.timeZone, zone)
        .appBackdrop()
        .navigationTitle("Can't work")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button("Cancel") { dismiss() }
            }
        }
    }
}
