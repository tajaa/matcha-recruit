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

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                HStack(spacing: 10) {
                    ActionTile(symbol: "calendar.badge.minus", title: "Can't work") { showUnavailable = true }
                    NavigationLink {
                        AvailabilityView { Task { await load() } }
                    } label: {
                        TileContent(symbol: "clock.arrow.2.circlepath", title: "Availability")
                    }
                    .buttonStyle(PressableStyle())
                    if profile.enabled_features.time_off {
                        NavigationLink { PTOView() } label: {
                            TileContent(symbol: "sun.horizon.fill", title: "Time off")
                        }
                        .buttonStyle(PressableStyle())
                    }
                }
                .rise()

                if let error { ErrorBanner(message: error) }

                VStack(alignment: .leading, spacing: 10) {
                    SectionTitle(title: "Waiting on you", trailing: offers.isEmpty ? nil : "\(offers.count)")
                    if !loaded && loading {
                        GlassPlaceholder(label: "Loading requests")
                    } else if offers.isEmpty {
                        QuietNote(symbol: "tray", text: "No offers from coworkers right now.")
                    } else {
                        ForEach(offers) { offer in
                            OfferCard(offer: offer, busy: busyID == offer.id, disabled: busyID != nil) {
                                Task { await accept(offer) }
                            }
                            .transition(.scale(scale: 0.96).combined(with: .opacity))
                        }
                    }
                }
                .rise(delay: 0.05)

                VStack(alignment: .leading, spacing: 10) {
                    SectionTitle(title: "Your requests")
                    if !loaded && loading {
                        GlassPlaceholder(label: "Loading requests")
                        GlassPlaceholder(label: "Loading requests")
                    } else if requests.isEmpty {
                        QuietNote(symbol: "arrow.left.arrow.right",
                                  text: "Swaps, drops and time off you ask for will show up here.")
                    } else {
                        ForEach(requests) { request in
                            RequestCard(
                                request: request,
                                canEnd: request.isPending && (
                                    request.employee_id == profile.id ||
                                    (request.status == "awaiting_manager" && request.target_employee_id == profile.id)
                                ),
                                busy: busyID == request.id,
                                disabled: busyID != nil
                            ) { Task { await end(request) } }
                        }
                    }
                }
                .rise(delay: 0.1)
            }
            .padding(.horizontal, Metrics.gutter)
            .padding(.bottom, 32)
            .animation(.spring(response: 0.45, dampingFraction: 0.86), value: offers.map(\.id))
            .animation(.spring(response: 0.45, dampingFraction: 0.86), value: requests.map(\.id))
        }
        .scrollIndicators(.hidden)
        .ambientBackground()
        .navigationTitle("Requests")
        .refreshable { await load() }
        .task { await load() }
        .sheet(isPresented: $showUnavailable) {
            NavigationStack {
                UnavailableView { Task { await load() } }
            }
            .presentationCornerRadius(32)
        }
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
        case "approved": Palette.leaf
        case "denied": Palette.alert
        case "awaiting_counterparty": Palette.dusk
        case "pending", "awaiting_manager": Palette.amber
        default: Palette.inkSoft
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
}

// MARK: - Cards

private struct OfferCard: View {
    let offer: ScheduleRequest
    let busy: Bool
    let disabled: Bool
    let onAccept: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(spacing: 12) {
                Avatar(name: offer.employee_name, size: 40)
                VStack(alignment: .leading, spacing: 2) {
                    Text(offer.request_type == "swap"
                         ? "\(offer.employee_name) wants to swap"
                         : "\(offer.employee_name) is offering a shift")
                        .font(TypeScale.headline).foregroundStyle(Palette.ink)
                    if let role = offer.shift_role {
                        Text(role).font(TypeScale.subhead).foregroundStyle(Palette.inkSoft)
                    }
                }
                Spacer(minLength: 0)
            }
            if let when = offer.shift_starts_at {
                let part = DayPart(wallClockISO: when)
                Label(WallClock.label(when, format: "EEEE, MMM d · h:mm a"), systemImage: part.symbol)
                    .font(TypeScale.callout)
                    .foregroundStyle(part.color)
                    .labelStyle(TightLabel())
            }
            Button(action: onAccept) {
                LoadingLabel(title: offer.request_type == "swap" ? "Accept swap" : "Take this shift", busy: busy)
            }
            .buttonStyle(PrimaryButtonStyle())
            .disabled(disabled)
        }
        .padding(16)
        .glassSurface(tint: Palette.leaf)
    }
}

private struct RequestCard: View {
    let request: ScheduleRequest
    let canEnd: Bool
    let busy: Bool
    let disabled: Bool
    let onEnd: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .top, spacing: 12) {
                Image(systemName: request.kindSymbol)
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundStyle(request.statusColor)
                    .frame(width: 36, height: 36)
                    .background(request.statusColor.opacity(0.13), in: Circle())
                VStack(alignment: .leading, spacing: 3) {
                    Text(request.kindLabel).font(TypeScale.headline).foregroundStyle(Palette.ink)
                    if let role = request.shift_role {
                        Text(role).font(TypeScale.subhead).foregroundStyle(Palette.inkSoft)
                    }
                    if let when = request.whenLine {
                        Text(when).font(TypeScale.subhead).foregroundStyle(Palette.inkSoft).monospacedDigit()
                    }
                }
                Spacer(minLength: 8)
                StatusPill(text: request.statusLabel, color: request.statusColor)
            }
            if let note = request.review_notes, !note.isEmpty {
                Label(note, systemImage: "quote.opening")
                    .font(TypeScale.subhead)
                    .foregroundStyle(Palette.inkSoft)
                    .padding(.leading, 48)
            }
            if canEnd {
                HStack {
                    Spacer()
                    Button(action: onEnd) {
                        if busy { ProgressView() } else { Text(request.status == "pending" ? "Cancel request" : "Withdraw") }
                    }
                    .buttonStyle(GlassButtonStyle(tint: Palette.alert))
                    .disabled(disabled)
                }
            }
        }
        .padding(16)
        .glassSurface(elevated: false)
    }
}

struct QuietNote: View {
    let symbol: String
    let text: String

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: symbol).foregroundStyle(Palette.inkFaint)
            Text(text).font(TypeScale.subhead).foregroundStyle(Palette.inkSoft)
            Spacer(minLength: 0)
        }
        .padding(16)
        .glassSurface(elevated: false)
    }
}

// MARK: - Can't work

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
            } header: {
                Eyebrow("Dates you can't work")
            } footer: {
                Text("Your manager sees this before building the schedule.").font(TypeScale.caption)
            }
            .listRowBackground(GlassRowBackground())
            Section {
                TextField("Why? (optional)", text: $reason, axis: .vertical).lineLimit(2...5)
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
                } label: {
                    LoadingLabel(title: "Send to my manager", busy: saving)
                }
                .buttonStyle(PrimaryButtonStyle())
                .disabled(saving || DateInput.date(end) < DateInput.date(start))
            }
            .listRowBackground(Color.clear)
            .listRowInsets(EdgeInsets())
        }
        .glassForm()
        .navigationTitle("Can't work")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button { dismiss() } label: { Text("Cancel").font(TypeScale.callout) }
            }
        }
    }
}
