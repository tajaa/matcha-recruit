import SwiftUI

/// "Add to calendar" from the email reader. The email agent reads the message
/// and proposes events (`/agent/email/calendar-suggest`); the person can steer
/// it ("only the dinner"), edit each one, untick what they don't want, and
/// nothing reaches the calendar until they press Add.
struct EmailCalendarSheet: View {
    @Environment(AppState.self) private var appState
    @Environment(\.workPane) private var pane
    @Environment(\.dismiss) private var dismiss
    let email: EmailMessage
    /// How many were added, and the first one's start.
    var onAdded: (Int, Date?) -> Void = { _, _ in }

    private enum Phase: Equatable { case finding, ready, failed(String) }

    @State private var instructions = ""
    @State private var phase: Phase = .finding
    @State private var drafts: [CalendarDraft] = []
    @State private var existing: [MWCalendarEvent] = []
    @State private var saving = false
    @State private var saveError: String?
    @State private var generation = 0
    @State private var addTask: Task<Void, Never>?

    private var chosen: [CalendarDraft] { drafts.filter(\.include) }
    private var canAdd: Bool {
        EmailCalendarRules.canAdd(ready: phase == .ready, saving: saving, drafts: drafts)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            header
            steerBar
            if !existing.isEmpty { alreadyThere }
            content
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
            footer
        }
        .padding(20)
        .frame(width: 560, height: 600)
        .background(appState.themeBg)
        .task { await find() }
        // Signing out tears the sheet down: stop a batch mid-way rather than
        // send its remaining events with whoever signs in next.
        .onDisappear { addTask?.cancel() }
    }

    // MARK: Parts

    private var header: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: "calendar.badge.plus")
                .font(.system(size: 18))
                .foregroundColor(appState.themeAccent)
            VStack(alignment: .leading, spacing: 2) {
                Text("Add to calendar")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(appState.themeText)
                Text("From “\(email.subject.isEmpty ? "(no subject)" : email.subject)”")
                    .font(.system(size: 11))
                    .foregroundColor(appState.themeTextSecondary)
                    .lineLimit(1)
            }
            Spacer()
        }
    }

    private var steerBar: some View {
        HStack(spacing: 6) {
            Image(systemName: "sparkles")
                .font(.system(size: 11))
                .foregroundColor(appState.themeAccent)
            TextField("Tell Espresso what to add (optional), e.g. “only the dinner, not the brunch”",
                      text: $instructions)
                .textFieldStyle(.plain)
                .font(.system(size: 12))
                .foregroundColor(appState.themeText)
                .onSubmit { Task { await find() } }
            Button {
                Task { await find() }
            } label: {
                if phase == .finding {
                    ProgressView().controlSize(.mini)
                } else {
                    Text(instructions.trimmingCharacters(in: .whitespaces).isEmpty ? "Find again" : "Find events")
                        .font(.system(size: 11, weight: .semibold))
                }
            }
            .buttonStyle(.plain)
            .foregroundColor(appState.themeAccent)
            .disabled(phase == .finding || saving)
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 7)
        .background(RoundedRectangle(cornerRadius: 7).fill(appState.themeAccent.opacity(0.06)))
        .overlay(RoundedRectangle(cornerRadius: 7).stroke(appState.themeAccent.opacity(0.25), lineWidth: 1))
    }

    private var alreadyThere: some View {
        VStack(alignment: .leading, spacing: 4) {
            Label("Already on your calendar from this email", systemImage: "checkmark.circle.fill")
                .font(.system(size: 11, weight: .semibold))
                .foregroundColor(.green)
            ForEach(existing) { event in
                Button {
                    dismiss()
                    appState.openCalendar(at: CalendarWire.date(event.start), in: pane)
                } label: {
                    HStack(spacing: 6) {
                        Text(event.title).font(.system(size: 11, weight: .medium)).lineLimit(1)
                        Text(Self.when(event.start, event.end, allDay: event.allDay))
                            .font(.system(size: 11))
                            .foregroundColor(appState.themeTextSecondary)
                        Spacer()
                        Image(systemName: "arrow.right.circle").font(.system(size: 10))
                    }
                    .foregroundColor(appState.themeText)
                }
                .buttonStyle(.plain)
            }
        }
        .padding(10)
        .background(RoundedRectangle(cornerRadius: 7).fill(Color.green.opacity(0.06)))
    }

    @ViewBuilder
    private var content: some View {
        switch phase {
        case .finding where drafts.isEmpty:
            VStack(spacing: 8) {
                ProgressView().controlSize(.small)
                Text("Reading the email for dates and times…")
                    .font(.system(size: 12))
                    .foregroundColor(appState.themeTextSecondary)
            }
            .frame(maxWidth: .infinity)
            .padding(.top, 60)
        case .failed(let message):
            VStack(spacing: 8) {
                Image(systemName: "exclamationmark.triangle")
                    .font(.system(size: 20))
                    .foregroundColor(.orange)
                Text(message)
                    .font(.system(size: 12))
                    .foregroundColor(appState.themeTextSecondary)
                    .multilineTextAlignment(.center)
                    .frame(maxWidth: 380)
                HStack(spacing: 12) {
                    Button("Try again") { Task { await find() } }
                    Button("Add one yourself", action: addBlank)
                }
                .buttonStyle(.plain)
                .font(.system(size: 12, weight: .semibold))
                .foregroundColor(appState.themeAccent)
            }
            .frame(maxWidth: .infinity)
            .padding(.top, 50)
        default:
            if drafts.isEmpty {
                VStack(spacing: 8) {
                    Image(systemName: "calendar")
                        .font(.system(size: 22))
                        .foregroundColor(appState.themeTextSecondary.opacity(0.7))
                    Text(existing.isEmpty ? "No events found in this email." : "Nothing new to add.")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundColor(appState.themeTextSecondary)
                    Button("Add one yourself", action: addBlank)
                        .buttonStyle(.plain)
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundColor(appState.themeAccent)
                }
                .frame(maxWidth: .infinity)
                .padding(.top, 50)
            } else {
                ScrollView {
                    VStack(spacing: 10) {
                        ForEach($drafts) { $draft in
                            EmailCalendarDraftCard(draft: $draft) {
                                drafts.removeAll { $0.id == draft.id }
                            }
                        }
                        Button(action: addBlank) {
                            Label("Add another", systemImage: "plus").font(.system(size: 11, weight: .medium))
                        }
                        .buttonStyle(.plain)
                        .foregroundColor(appState.themeTextSecondary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                    }
                }
                .opacity(phase == .finding ? 0.5 : 1)
            }
        }
    }

    private var footer: some View {
        HStack {
            if let saveError {
                Label(saveError, systemImage: "exclamationmark.triangle.fill")
                    .font(.system(size: 11))
                    .foregroundColor(.orange)
                    .lineLimit(2)
            } else if let problem = chosen.compactMap(\.problem).first {
                Text(problem).font(.system(size: 11)).foregroundColor(.orange)
            }
            Spacer()
            Button("Cancel") { dismiss() }
                .keyboardShortcut(.cancelAction)
            Button(action: { addTask = Task { await add() } }) {
                if saving {
                    ProgressView().controlSize(.small)
                } else {
                    Text(chosen.count > 1 ? "Add \(chosen.count) to calendar" : "Add to calendar")
                }
            }
            .keyboardShortcut(.defaultAction)
            .buttonStyle(.borderedProminent)
            .tint(appState.themeAccent)
            .disabled(!canAdd)
        }
    }

    // MARK: Actions

    private func find() async {
        // A rescan mid-save would swap the list the batch is writing.
        guard !saving else { return }
        generation += 1
        let gen = generation
        phase = .finding
        saveError = nil
        do {
            let response = try await CalendarService.shared.suggestFromEmail(
                emailId: email.id, instructions: instructions)
            guard gen == generation else { return }
            drafts = EmailCalendarRules.markRepeats(
                response.events.compactMap { CalendarDraft(suggestion: $0) }, existing: response.existing)
            existing = response.existing
            phase = .ready
        } catch {
            guard gen == generation else { return }
            phase = .failed(error.localizedDescription)
        }
    }

    private func addBlank() {
        drafts.append(CalendarDraft(on: Date(), title: email.subject))
        phase = .ready
    }

    private func add() async {
        guard canAdd else { return }
        saving = true
        saveError = nil
        // The account that pressed Add. Every request carries whoever's token
        // is current when it is sent, so each event re-checks this first.
        let owner = appState.currentUser?.id
        let outcome = await EmailCalendarRules.add(
            chosen, emailId: email.id, subject: email.subject, backend: CalendarService.shared,
            stillOwner: { owner != nil && appState.isAuthenticated && appState.currentUser?.id == owner }
        )
        saving = false
        guard !outcome.stopped else { return }
        drafts.removeAll { outcome.added.contains($0.id) }
        saveError = outcome.error
        if !outcome.added.isEmpty { onAdded(outcome.added.count, outcome.firstStart) }
        if saveError == nil { dismiss() }
    }

    static func when(_ start: String, _ end: String, allDay: Bool) -> String {
        guard let s = CalendarWire.date(start) else { return start }
        if allDay {
            let e = CalendarWire.date(end) ?? s
            let day = s.formatted(.dateTime.weekday(.abbreviated).month(.abbreviated).day())
            return Calendar.current.isDate(s, inSameDayAs: e)
                ? day : "\(day) – \(e.formatted(.dateTime.month(.abbreviated).day()))"
        }
        return s.formatted(.dateTime.weekday(.abbreviated).month(.abbreviated).day().hour().minute())
    }
}

/// The sheet's rules, kept apart from the view so they can be tested.
@MainActor
enum EmailCalendarRules {
    /// Save only a finished scan's list: during a rescan, or after one failed,
    /// the drafts on hand are not what the person asked for last.
    static func canAdd(ready: Bool, saving: Bool, drafts: [CalendarDraft]) -> Bool {
        let chosen = drafts.filter(\.include)
        return ready && !saving && !chosen.isEmpty && chosen.allSatisfy { $0.problem == nil }
    }

    /// Proposals this email already put on the calendar start unticked, so
    /// adding one again is a deliberate choice. A match is the same start
    /// (minute, or day for all day), or the same title on the same day.
    static func markRepeats(_ drafts: [CalendarDraft], existing: [MWCalendarEvent],
                            calendar: Calendar = .current) -> [CalendarDraft] {
        let known = existing.compactMap { event -> (title: String, start: Date, allDay: Bool)? in
            CalendarWire.date(event.start, calendar: calendar).map {
                (event.title.trimmingCharacters(in: .whitespacesAndNewlines).lowercased(), $0, event.allDay)
            }
        }
        return drafts.map { draft in
            let title = draft.trimmedTitle.lowercased()
            let repeated = known.contains { event in
                let sameDay = calendar.isDate(event.start, inSameDayAs: draft.start)
                let sameStart = event.allDay == draft.allDay
                    && (draft.allDay ? sameDay : abs(event.start.timeIntervalSince(draft.start)) < 60)
                return sameStart || (sameDay && event.title == title)
            }
            guard repeated else { return draft }
            var marked = draft
            marked.include = false
            marked.alreadyOnCalendar = true
            return marked
        }
    }

    struct AddOutcome {
        var added: [UUID] = []
        var firstStart: Date?
        var error: String?
        /// The sheet went away or the account changed; nothing more was sent.
        var stopped = false
    }

    /// Add `drafts` one at a time, stopping before any request once the task
    /// is cancelled or `stillOwner` says the account that started it is gone.
    static func add(_ drafts: [CalendarDraft], emailId: String, subject: String,
                    backend: CalendarBackend, calendar: Calendar = .current,
                    stillOwner: () -> Bool) async -> AddOutcome {
        var outcome = AddOutcome()
        for draft in drafts {
            guard !Task.isCancelled, stillOwner() else {
                outcome.stopped = true
                return outcome
            }
            do {
                _ = try await backend.createEvent(
                    draft.fields(calendar: calendar), sourceKind: "email", sourceRef: emailId,
                    sourceLabel: subject.isEmpty ? nil : subject)
                outcome.added.append(draft.id)
                outcome.firstStart = outcome.firstStart.map { min($0, draft.start) } ?? draft.start
            } catch {
                outcome.error = "Couldn't add “\(draft.trimmedTitle)”: \(error.localizedDescription)"
                break
            }
        }
        return outcome
    }
}

/// One proposed event: keep or skip it, and fix what the agent got wrong.
private struct EmailCalendarDraftCard: View {
    @Environment(AppState.self) private var appState
    @Binding var draft: CalendarDraft
    let onRemove: () -> Void

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Toggle("", isOn: $draft.include)
                .toggleStyle(.checkbox)
                .labelsHidden()
                .padding(.top, 3)
            VStack(alignment: .leading, spacing: 8) {
                TextField("Title", text: $draft.title)
                    .textFieldStyle(.plain)
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundColor(appState.themeText)
                CalendarTimeFields(draft: $draft, compact: true)
                HStack(spacing: 6) {
                    Image(systemName: "mappin.and.ellipse")
                        .font(.system(size: 10))
                        .foregroundColor(appState.themeTextSecondary)
                    TextField("Location", text: $draft.location)
                        .textFieldStyle(.plain)
                        .font(.system(size: 11))
                        .foregroundColor(appState.themeText)
                }
                if draft.alreadyOnCalendar {
                    Label("Already on your calendar from this email. Tick it to add it again.",
                          systemImage: "checkmark.circle")
                        .font(.system(size: 10.5))
                        .foregroundColor(.orange)
                }
                if !draft.notes.isEmpty {
                    Text(draft.notes)
                        .font(.system(size: 11))
                        .foregroundColor(appState.themeTextSecondary)
                        .lineLimit(2)
                }
            }
            .opacity(draft.include ? 1 : 0.45)
            Spacer(minLength: 0)
            Button(action: onRemove) {
                Image(systemName: "xmark")
                    .font(.system(size: 9, weight: .bold))
                    .foregroundColor(appState.themeTextSecondary)
            }
            .buttonStyle(.plain)
            .help("Remove")
        }
        .padding(12)
        .background(RoundedRectangle(cornerRadius: 9).fill(appState.themeText.opacity(0.04)))
        .overlay(RoundedRectangle(cornerRadius: 9).stroke(appState.themeBorder.opacity(0.6), lineWidth: 0.5))
    }
}
