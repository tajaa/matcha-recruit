import SwiftUI

/// Create or edit one event on the person's Espresso calendar.
struct CalendarEventEditor: View {
    @Environment(AppState.self) private var appState
    @Environment(\.workPane) private var pane
    @Environment(\.dismiss) private var dismiss
    let request: CalendarEditorRequest
    let onSave: (CalendarDraft) async throws -> Void
    let onDelete: (() async throws -> Void)?

    @State private var draft: CalendarDraft
    @State private var saving = false
    @State private var error: String?
    @State private var confirmDelete = false
    @FocusState private var titleFocused: Bool

    init(request: CalendarEditorRequest,
         onSave: @escaping (CalendarDraft) async throws -> Void,
         onDelete: (() async throws -> Void)?) {
        self.request = request
        self.onSave = onSave
        self.onDelete = onDelete
        _draft = State(initialValue: request.draft)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(spacing: 8) {
                Image(systemName: request.event == nil ? "calendar.badge.plus" : "calendar")
                    .font(.system(size: 13))
                    .foregroundColor(appState.themeAccent)
                Text(request.event == nil ? "New event" : "Edit event")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundColor(appState.themeText)
                Spacer()
            }

            TextField("Title", text: $draft.title)
                .textFieldStyle(.plain)
                .font(.system(size: 17, weight: .semibold))
                .foregroundColor(appState.themeText)
                .focused($titleFocused)
                .onSubmit(save)

            CalendarTimeFields(draft: $draft)

            labeled("Location", icon: "mappin.and.ellipse") {
                TextField("Add a place", text: $draft.location)
                    .textFieldStyle(.plain)
                    .font(.system(size: 12))
            }
            labeled("Notes", icon: "text.alignleft") {
                TextEditor(text: $draft.notes)
                    .font(.system(size: 12))
                    .scrollContentBackground(.hidden)
                    .frame(minHeight: 70, maxHeight: 140)
                    .overlay(alignment: .topLeading) {
                        if draft.notes.isEmpty {
                            Text("Notes")
                                .font(.system(size: 12))
                                .foregroundColor(appState.themeTextSecondary.opacity(0.7))
                                .padding(.leading, 5)
                                .allowsHitTesting(false)
                        }
                    }
            }

            if let event = request.event {
                sourceFooter(event)
            }

            if let message = error ?? (draft.trimmedTitle.isEmpty ? nil : draft.problem) {
                Label(message, systemImage: "exclamationmark.triangle.fill")
                    .font(.system(size: 11))
                    .foregroundColor(.orange)
            }

            HStack {
                if onDelete != nil {
                    Button("Delete", role: .destructive) { confirmDelete = true }
                        .disabled(saving)
                }
                Spacer()
                Button("Cancel") { dismiss() }
                    .keyboardShortcut(.cancelAction)
                Button(action: save) {
                    if saving { ProgressView().controlSize(.small) } else { Text("Save") }
                }
                .keyboardShortcut(.defaultAction)
                .buttonStyle(.borderedProminent)
                .tint(appState.themeAccent)
                .disabled(saving || draft.problem != nil)
            }
        }
        .padding(20)
        .frame(width: 460)
        .background(appState.themeBg)
        .onAppear { if request.event == nil { titleFocused = true } }
        .confirmationDialog("Delete “\(draft.trimmedTitle)”?", isPresented: $confirmDelete) {
            Button("Delete event", role: .destructive, action: delete)
        } message: {
            Text("It is removed from your Espresso calendar.")
        }
    }

    @ViewBuilder
    private func sourceFooter(_ event: MWCalendarEvent) -> some View {
        switch event.sourceKind {
        case "email":
            HStack(spacing: 6) {
                Image(systemName: "envelope").font(.system(size: 10))
                Text("From email" + (event.sourceLabel.map { ": \($0)" } ?? ""))
                    .font(.system(size: 11))
                    .lineLimit(1)
                Spacer()
                if let id = event.sourceRef {
                    Button("Open email") {
                        dismiss()
                        appState.openEmail(id: id, in: pane)
                    }
                    .buttonStyle(.plain)
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundColor(appState.themeAccent)
                }
            }
            .foregroundColor(appState.themeTextSecondary)
        case "assistant":
            Label("Added by Espresso", systemImage: "sparkles")
                .font(.system(size: 11))
                .foregroundColor(appState.themeTextSecondary)
        default:
            EmptyView()
        }
    }

    private func labeled<Content: View>(_ label: String, icon: String, @ViewBuilder content: () -> Content) -> some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: icon)
                .font(.system(size: 11))
                .foregroundColor(appState.themeTextSecondary)
                .frame(width: 16)
                .padding(.top, 2)
                .help(label)
            content()
                .foregroundColor(appState.themeText)
        }
        .padding(8)
        .background(RoundedRectangle(cornerRadius: 7).fill(appState.themeText.opacity(0.04)))
    }

    private func save() {
        guard !saving, draft.problem == nil else { return }
        saving = true
        error = nil
        Task {
            do {
                try await onSave(draft)
                dismiss()
            } catch {
                self.error = error.localizedDescription
            }
            saving = false
        }
    }

    private func delete() {
        guard let onDelete else { return }
        saving = true
        Task {
            do {
                try await onDelete()
                dismiss()
            } catch {
                self.error = error.localizedDescription
            }
            saving = false
        }
    }
}

/// All-day switch and start/end pickers. Moving the start moves the end with
/// it (the length stays, in whole days when all day), like Calendar.app.
struct CalendarTimeFields: View {
    @Environment(AppState.self) private var appState
    @Binding var draft: CalendarDraft
    var compact = false

    var body: some View {
        VStack(alignment: .leading, spacing: compact ? 6 : 8) {
            Toggle("All day", isOn: Binding(get: { draft.allDay }, set: setAllDay))
                .toggleStyle(.switch)
                .controlSize(.mini)
                .font(.system(size: 11))
                .foregroundColor(appState.themeTextSecondary)
            HStack(spacing: 8) {
                row("Starts", selection: Binding(get: { draft.start }, set: setStart))
                Image(systemName: "arrow.right")
                    .font(.system(size: 9))
                    .foregroundColor(appState.themeTextSecondary)
                row("Ends", selection: $draft.end)
            }
        }
    }

    private func row(_ label: String, selection: Binding<Date>) -> some View {
        DatePicker(label, selection: selection,
                   displayedComponents: draft.allDay ? [.date] : [.date, .hourAndMinute])
            .datePickerStyle(.compact)
            .labelsHidden()
            .font(.system(size: 12))
            .help(label)
    }

    private func setStart(_ next: Date) {
        draft = draft.movingStart(to: next)
    }

    private func setAllDay(_ on: Bool) {
        guard on != draft.allDay else { return }
        let cal = Calendar.current
        if on {
            draft.start = cal.startOfDay(for: draft.start)
            draft.end = max(draft.start, cal.startOfDay(for: draft.end))
        } else {
            let fresh = CalendarDraft(on: draft.start)
            draft.start = fresh.start
            draft.end = fresh.end
        }
        draft.allDay = on
    }
}
