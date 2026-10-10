import SwiftUI

/// Schedule requests waiting for this manager and, for a business admin,
/// paid time off. Approving can hit a conflict the manager may override.
struct ApprovalsView: View {
    @Environment(AppState.self) private var appState
    let scope: ManagerScope
    let location: ManagedLocation?
    @State private var requests: [ScheduleRequest] = []
    @State private var timeOff: [PTOAdminRequest] = []
    @State private var loading = false
    @State private var loaded = false
    @State private var error: String?
    /// The one review sheet, by what it reviews.
    @State private var reviewing: Review?

    private enum Review: Identifiable {
        case request(ScheduleRequest)
        case timeOff(PTOAdminRequest)

        var id: String {
            switch self {
            case .request(let request): "request-\(request.id)"
            case .timeOff(let request): "pto-\(request.id)"
            }
        }
    }

    /// Time off is company-wide data, so it belongs to business admins only.
    private var showsTimeOff: Bool { scope.company_wide && scope.features.time_off }

    var body: some View {
        List {
            if let error {
                ErrorRow(message: error) { Task { await load() } }.cardRow()
            }

            SectionLabel("Shift requests")
            if !loaded && loading {
                placeholderRow
                placeholderRow
            } else if requests.isEmpty {
                Text("Swaps, drops, open shift claims and time away land here for you to approve.")
                    .foregroundStyle(Color.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .cardRow()
            } else {
                ForEach(requests) { request in
                    Button { reviewing = .request(request) } label: {
                        ManagerRequestRow(request: request, store: storeName(request.location_id))
                    }
                    .buttonStyle(.plain)
                    .cardRow()
                    .accessibilityIdentifier("approvals.request")
                }
            }

            if showsTimeOff {
                SectionLabel("Paid time off")
                if loaded && timeOff.isEmpty {
                    Text("No time off waiting.")
                        .foregroundStyle(Color.secondary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .cardRow()
                } else {
                    ForEach(timeOff) { item in
                        Button { reviewing = .timeOff(item) } label: { TimeOffRow(request: item) }
                            .buttonStyle(.plain)
                            .cardRow()
                    }
                }
            }
        }
        .listStyle(.plain)
        .appBackdrop()
        .animation(.default, value: requests.map(\.id))
        .animation(.default, value: timeOff.map(\.id))
        .refreshable { await load() }
        .task(id: location?.id) { await load() }
        .onChange(of: appState.pendingApprovalID) { _, _ in openPendingApproval() }
        .sheet(item: $reviewing) { item in
            NavigationStack {
                switch item {
                case .request(let request):
                    RequestReviewView(request: request, store: storeName(request.location_id)) {
                        Task { await load() }
                    }
                case .timeOff(let request):
                    TimeOffReviewView(request: request) { Task { await load() } }
                }
            }
        }
    }

    private var placeholderRow: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text("Avery wants to swap").font(.app(.headline))
            Text("Monday, Jan 1 · 9:00 AM").font(.app(.subheadline))
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .redacted(reason: .placeholder)
        .cardRow()
        .accessibilityLabel("Loading requests")
    }

    /// Only worth saying when the list spans stores.
    private func storeName(_ id: String?) -> String? {
        guard location == nil, scope.locations.count > 1, let id else { return nil }
        return scope.locations.first { $0.id == id }?.displayName
    }

    private func load() async {
        loading = true
        error = nil
        do {
            requests = try await ManagerService.requests(location: location?.id)
            if showsTimeOff { timeOff = try await ManagerService.pendingPTO() }
        } catch {
            if !error.isCancellation { self.error = error.localizedDescription }
        }
        loading = false
        loaded = true
        openPendingApproval()
        await appState.refreshBadges()
    }

    /// A push or link named a request: open it once it is on screen. One
    /// already reviewed elsewhere is simply gone from the list.
    private func openPendingApproval() {
        guard loaded, let id = appState.pendingApprovalID else { return }
        appState.pendingApprovalID = nil
        if let request = requests.first(where: { $0.id == id }) { reviewing = .request(request) }
    }
}

// MARK: - Vocabulary
//
// The same requests a crew member sees under Requests, in a manager's words.

extension ScheduleRequest {
    var managerHeadline: String {
        let target = target_employee_name?.isEmpty == false ? target_employee_name! : "a coworker"
        switch request_type {
        case "swap": return "\(employee_name) and \(target) want to swap"
        case "pickup": return "\(target) is taking \(employee_name)'s shift"
        case "drop": return "\(employee_name) wants to drop a shift"
        case "claim": return "\(employee_name) wants an open shift"
        case "unavailable": return "\(employee_name) can't work"
        case "availability": return "\(employee_name) is changing availability"
        default: return "\(employee_name): \(kindLabel)"
        }
    }

    /// The proposed weekly availability, one line per window.
    var availabilityLines: [String] {
        guard let proposal = proposed_availability else { return [] }
        if proposal.availability_state == "always_available" { return ["Available any time"] }
        let days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
        return proposal.windows
            .sorted { ($0.weekday, $0.start_time) < ($1.weekday, $1.start_time) }
            .map { window in
                let day = (0..<7).contains(window.weekday) ? days[window.weekday] : "Day \(window.weekday)"
                return "\(day) \(WallClock.clockTime(window.start_time)) – \(WallClock.clockTime(window.end_time))"
            }
    }
}

private struct ManagerRequestRow: View {
    let request: ScheduleRequest
    let store: String?

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Avatar(name: request.employee_name, size: 36)
            VStack(alignment: .leading, spacing: 4) {
                Text(request.managerHeadline)
                    .font(.app(.headline))
                    .foregroundStyle(Color.primary)
                    .multilineTextAlignment(.leading)
                Label(request.kindLabel, systemImage: request.kindSymbol)
                    .labelStyle(TightLabel())
                    .font(.app(.caption, .medium))
                    .foregroundStyle(Color.secondary)
                if let when = request.offeredShiftLine ?? request.whenLine {
                    Text(when).font(.app(.subheadline)).foregroundStyle(Color.secondary).monospacedDigit()
                }
                if let wanted = request.counterShiftLine {
                    Text("For: \(wanted)").font(.app(.subheadline)).foregroundStyle(Color.secondary).monospacedDigit()
                }
                if let store {
                    Label(store, systemImage: "storefront").labelStyle(TightLabel())
                        .font(.app(.caption)).foregroundStyle(Color.secondary)
                }
            }
            Spacer(minLength: 0)
            Image(systemName: "chevron.right")
                .font(.app(.caption, .semibold))
                .foregroundStyle(Color.secondary)
                .padding(.top, 4)
        }
        .contentShape(Rectangle())
    }
}

private struct TimeOffRow: View {
    let request: PTOAdminRequest

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Avatar(name: request.employee_name, size: 36)
            VStack(alignment: .leading, spacing: 4) {
                Text(request.employee_name).font(.app(.headline)).foregroundStyle(Color.primary)
                Text("\(request.kindLabel) · \(request.hoursLine)")
                    .font(.app(.subheadline)).foregroundStyle(Color.secondary)
                Text(request.datesLine).font(.app(.subheadline)).foregroundStyle(Color.secondary)
            }
            Spacer(minLength: 0)
            Image(systemName: "chevron.right")
                .font(.app(.caption, .semibold))
                .foregroundStyle(Color.secondary)
                .padding(.top, 4)
        }
        .contentShape(Rectangle())
    }
}

// MARK: - Review

struct RequestReviewView: View {
    @Environment(\.dismiss) private var dismiss
    let request: ScheduleRequest
    let store: String?
    let onDone: () -> Void
    @State private var notes = ""
    @State private var busy: Bool?
    @State private var error: String?
    @State private var force: ForcePrompt?

    var body: some View {
        Form {
            Section {
                VStack(alignment: .leading, spacing: 6) {
                    Label(request.kindLabel, systemImage: request.kindSymbol)
                        .labelStyle(TightLabel())
                        .font(.app(.caption, .medium))
                        .foregroundStyle(Color.secondary)
                    Text(request.managerHeadline).font(.app(.headline))
                }
                if let shift = request.offeredShiftLine {
                    LabeledContent(request.request_type == "swap" ? "\(request.employee_name)'s shift" : "Shift") {
                        Text(shift).multilineTextAlignment(.trailing)
                    }
                }
                if let counter = request.counterShiftLine {
                    LabeledContent("\(request.target_employee_name ?? "Coworker")'s shift") {
                        Text(counter).multilineTextAlignment(.trailing)
                    }
                }
                if request.offeredShiftLine == nil, let when = request.whenLine {
                    LabeledContent("When", value: when)
                }
                if let store { LabeledContent("Store", value: store) }
                if let reason = request.reason, !reason.isEmpty {
                    Text("\u{201C}\(reason)\u{201D}").foregroundStyle(Color.secondary)
                }
            }
            .monospacedDigit()

            if !request.availabilityLines.isEmpty {
                Section("New weekly availability") {
                    ForEach(request.availabilityLines, id: \.self) { Text($0) }
                }
            }

            Section {
                TextField("Note to \(request.employee_name) (optional)", text: $notes, axis: .vertical)
                    .lineLimit(2...5)
            } footer: {
                Text("Approving changes the schedule right away. Everyone involved is notified.")
            }

            if let error {
                Section { ErrorRow(message: error) }
            }

            Section {
                Button { Task { await decide(approve: true) } } label: {
                    LoadingLabel(title: "Approve", busy: busy == true)
                }
                .primaryActionRow()
                .disabled(busy != nil)
                .accessibilityIdentifier("review.approve")
            }
            Section {
                Button(role: .destructive) { Task { await decide(approve: false) } } label: {
                    if busy == false { ProgressView() } else { Text("Deny").frame(maxWidth: .infinity) }
                }
                .disabled(busy != nil)
                .accessibilityIdentifier("review.deny")
            }
        }
        .appBackdrop()
        .navigationTitle("Review request")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) { Button("Close") { dismiss() } }
        }
        .forcePrompt($force) { message in
            error = message
            onDone()
        }
    }

    private func decide(approve: Bool) async {
        busy = approve
        error = nil
        defer { busy = nil }
        let note = notes.trimmingCharacters(in: .whitespacesAndNewlines)
        let review = { (force: Bool) in
            try await ManagerService.review(request, approve: approve, notes: note.isEmpty ? nil : note, force: force)
            onDone()
            dismiss()
        }
        do {
            try await ForcePrompt.run($force, review)
        } catch {
            // Most often someone else reviewed it first: the list behind is stale.
            self.error = error.localizedDescription
            onDone()
        }
    }
}

struct TimeOffReviewView: View {
    @Environment(\.dismiss) private var dismiss
    let request: PTOAdminRequest
    let onDone: () -> Void
    @State private var reason = ""
    @State private var busy: Bool?
    @State private var error: String?

    var body: some View {
        Form {
            Section {
                Text(request.employee_name).font(.app(.headline))
                LabeledContent("Type", value: request.kindLabel)
                LabeledContent("Dates", value: request.datesLine)
                LabeledContent("Hours", value: request.hoursLine)
                if let note = request.reason, !note.isEmpty {
                    Text("\u{201C}\(note)\u{201D}").foregroundStyle(Color.secondary)
                }
            }
            Section {
                TextField("Reason if you deny it (optional)", text: $reason, axis: .vertical)
                    .lineLimit(2...4)
            } footer: {
                Text("Approving draws the hours from their balance.")
            }
            if let error {
                Section { ErrorRow(message: error) }
            }
            Section {
                Button { Task { await decide(approve: true) } } label: {
                    LoadingLabel(title: "Approve", busy: busy == true)
                }
                .primaryActionRow()
                .disabled(busy != nil)
            }
            Section {
                Button(role: .destructive) { Task { await decide(approve: false) } } label: {
                    if busy == false { ProgressView() } else { Text("Deny").frame(maxWidth: .infinity) }
                }
                .disabled(busy != nil)
            }
        }
        .appBackdrop()
        .navigationTitle("Time off")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) { Button("Close") { dismiss() } }
        }
    }

    private func decide(approve: Bool) async {
        busy = approve
        error = nil
        defer { busy = nil }
        let note = reason.trimmingCharacters(in: .whitespacesAndNewlines)
        do {
            try await ManagerService.decidePTO(request, approve: approve, denialReason: approve || note.isEmpty ? nil : note)
            onDone()
            dismiss()
        } catch {
            self.error = error.localizedDescription
            onDone()
        }
    }
}
