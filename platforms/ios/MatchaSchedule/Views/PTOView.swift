import SwiftUI

struct PTOView: View {
    @State private var summary: PTOSummary?
    @State private var error: String?
    @State private var busyID: String?
    @State private var showForm = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                if let error { ErrorBanner(message: error) }
                if let summary {
                    balanceCard(summary.balance.balance_hours).rise()

                    VStack(alignment: .leading, spacing: 10) {
                        SectionTitle(title: "Waiting for approval")
                        if summary.pending_requests.isEmpty {
                            QuietNote(symbol: "hourglass", text: "Nothing pending.")
                        }
                        ForEach(summary.pending_requests) { request in
                            PTORow(request: request, pending: true, busy: busyID == request.id,
                                   disabled: busyID != nil) { Task { await cancel(request) } }
                        }
                    }
                    .rise(delay: 0.05)

                    VStack(alignment: .leading, spacing: 10) {
                        SectionTitle(title: "Approved this year")
                        if summary.approved_requests.isEmpty {
                            QuietNote(symbol: "sun.max", text: "No approved time off yet this year.")
                        }
                        ForEach(summary.approved_requests) { request in
                            PTORow(request: request, pending: false, busy: false, disabled: true) {}
                        }
                    }
                    .rise(delay: 0.1)
                } else if error == nil {
                    ProgressView().frame(maxWidth: .infinity).padding(.top, 60)
                }
            }
            .padding(.horizontal, Metrics.gutter)
            .padding(.bottom, 32)
        }
        .scrollIndicators(.hidden)
        .ambientBackground(.opener)
        .navigationTitle("Time off")
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button { showForm = true } label: { Text("Request").font(TypeScale.callout) }
            }
        }
        .refreshable { await load() }
        .task { await load() }
        .sheet(isPresented: $showForm) {
            NavigationStack {
                PTORequestForm { Task { await load() } }
            }
            .presentationCornerRadius(32)
        }
    }

    private func balanceCard(_ hours: String) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Label("Available".uppercased(), systemImage: "sun.horizon.fill")
                .font(TypeScale.eyebrow).tracking(1.4)
                .foregroundStyle(Palette.dawn)
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text(Self.trimmed(hours))
                    .font(.interDisplay(56, .bold, relativeTo: .largeTitle))
                    .monospacedDigit()
                    .foregroundStyle(Palette.ink)
                    .contentTransition(.numericText())
                Text("hours").font(TypeScale.title).foregroundStyle(Palette.inkSoft)
            }
            Button { showForm = true } label: { Label("Request time off", systemImage: "plus") }
                .buttonStyle(GlassButtonStyle(tint: Palette.leaf))
                .padding(.top, 6)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(22)
        .background(alignment: .topTrailing) {
            Image(systemName: "sun.horizon.fill")
                .font(.system(size: 130))
                .foregroundStyle(Palette.dawn.opacity(0.14))
                .offset(x: 30, y: -10)
                .accessibilityHidden(true)
        }
        .clipShape(RoundedRectangle(cornerRadius: Metrics.heroRadius, style: .continuous))
        .glassSurface(cornerRadius: Metrics.heroRadius, tint: Palette.dawn)
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
        HStack(alignment: .center, spacing: 12) {
            Image(systemName: request.request_type == "sick" ? "cross.case.fill" : "sun.max.fill")
                .font(.system(size: 15, weight: .semibold))
                .foregroundStyle(pending ? Palette.amber : Palette.leaf)
                .frame(width: 36, height: 36)
                .background((pending ? Palette.amber : Palette.leaf).opacity(0.14), in: Circle())
            VStack(alignment: .leading, spacing: 3) {
                Text(request.request_type.capitalized).font(TypeScale.headline).foregroundStyle(Palette.ink)
                Text(range + " · \(PTOView.trimmed(request.hours)) h")
                    .font(TypeScale.subhead).foregroundStyle(Palette.inkSoft).monospacedDigit()
            }
            Spacer()
            if pending {
                Button(action: onCancel) {
                    if busy { ProgressView() } else { Text("Cancel") }
                }
                .buttonStyle(GlassButtonStyle(tint: Palette.alert))
                .disabled(disabled)
            }
        }
        .padding(14)
        .glassSurface(elevated: false)
    }

    private var range: String {
        request.start_date == request.end_date
            ? DateInput.display(request.start_date, pattern: "EEE, MMM d")
            : "\(DateInput.display(request.start_date)) – \(DateInput.display(request.end_date))"
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
                Picker("Kind", selection: $type) {
                    Text("Vacation").tag("vacation")
                    Text("Sick").tag("sick")
                    Text("Personal").tag("personal")
                    Text("Other").tag("other")
                }
                .pickerStyle(.segmented)
                .listRowBackground(Color.clear)
                .listRowInsets(EdgeInsets())
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
                Eyebrow("Dates")
            }
            .listRowBackground(GlassRowBackground())
            Section {
                TextField("Add a note (optional)", text: $reason, axis: .vertical).lineLimit(2...4)
            } header: {
                Eyebrow("Note for your manager")
            }
            .listRowBackground(GlassRowBackground())
            if let error {
                Section { ErrorBanner(message: error) }
                    .listRowBackground(Color.clear).listRowInsets(EdgeInsets())
            }
            Section {
                Button { Task { await submit() } } label: {
                    ZStack {
                        Text("Send request").opacity(saving ? 0 : 1)
                        if saving { ProgressView().tint(.white) }
                    }
                }
                .buttonStyle(PrimaryButtonStyle())
                .disabled(saving)
            }
            .listRowBackground(Color.clear)
            .listRowInsets(EdgeInsets())
        }
        .glassForm(.opener)
        .navigationTitle("Request time off")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button { dismiss() } label: { Text("Cancel").font(TypeScale.callout) }
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
                start_date: DateInput.date(start), end_date: DateInput.date(end),
                hours: normalizedHours, reason: reason.isEmpty ? nil : reason,
                request_type: type
            ))
            onSaved()
            dismiss()
        } catch { self.error = error.localizedDescription }
    }
}
