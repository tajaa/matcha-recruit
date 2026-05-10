import SwiftUI

/// Right-pane journal view: header (title + collaborators + invite + style),
/// composer at top for a new entry today, timeline grouped by date below.
/// Editor uses `RichJournalEditor` (NSTextView-backed) with a toolbar of
/// markdown shortcuts; read mode renders via `JournalContentView` (handles
/// headers, bullets, todos, images, highlight, etc).
struct JournalDetailView: View {
    let journalId: String

    @Environment(AppState.self) private var appState
    @State private var vm = JournalDetailViewModel()
    @State private var composerOpen = false
    @State private var composerTitle = ""
    @State private var composerContent = ""
    @State private var composerDate: Date = Date()
    @State private var editingEntryId: String? = nil
    @State private var editingDraft: String = ""
    @State private var editingTitle: String = ""
    @State private var editingDate: Date = Date()
    @State private var showInviteSheet = false
    @State private var showStylePopover = false
    @State private var pendingDelete: MWJournalEntry? = nil
    @StateObject private var composerController = JournalEditorController()
    @StateObject private var editController = JournalEditorController()

    // Style preferences keyed by journal — read with @AppStorage so the
    // editor + renderer update as soon as the user changes them.
    @AppStorage private var fontFamily: String
    @AppStorage private var fontSizeRaw: Double
    @AppStorage private var lineSpacingRaw: Double

    init(journalId: String) {
        self.journalId = journalId
        _fontFamily = AppStorage(wrappedValue: "system", "journal.\(journalId).font.family")
        _fontSizeRaw = AppStorage(wrappedValue: 13.0, "journal.\(journalId).font.size")
        _lineSpacingRaw = AppStorage(wrappedValue: 3.0, "journal.\(journalId).line.spacing")
    }

    private var fontSize: CGFloat { CGFloat(fontSizeRaw) }
    private var lineSpacing: CGFloat { CGFloat(lineSpacingRaw) }

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider().opacity(0.2)
            composer
            Divider().opacity(0.2)
            timeline
        }
        .background(Color.appBackground)
        .task(id: journalId) { await vm.load(id: journalId) }
        .onAppear { wireUploadCallbacks() }
        .onChange(of: journalId) { _, _ in wireUploadCallbacks() }
        .sheet(isPresented: $showInviteSheet) {
            InviteToJournalSheet(
                journalId: journalId,
                journalTitle: vm.journal?.title ?? "journal",
            ) { _ in Task { await vm.refresh() } }
        }
        .confirmationDialog(
            "Delete this entry?",
            isPresented: Binding(
                get: { pendingDelete != nil },
                set: { if !$0 { pendingDelete = nil } }
            ),
            presenting: pendingDelete,
        ) { entry in
            Button("Delete", role: .destructive) {
                let target = entry
                pendingDelete = nil
                Task { await vm.deleteEntry(target) }
            }
            Button("Cancel", role: .cancel) { pendingDelete = nil }
        } message: { _ in Text("This cannot be undone.") }
    }

    /// Both controllers share a single upload path through the VM.
    /// Re-wire when the journalId changes so uploads target the right
    /// journal.
    private func wireUploadCallbacks() {
        let uploader: (Data, String, String) async -> String? = { [vm] data, name, mime in
            await vm.uploadImage(data: data, filename: name, mimeType: mime)
        }
        composerController.onUploadImage = uploader
        editController.onUploadImage = uploader
    }

    // MARK: - Header

    private var header: some View {
        HStack(spacing: 8) {
            Image(systemName: vm.journal?.icon ?? "book")
                .font(.system(size: 14))
                .foregroundColor(Color.matcha500)
            Text(vm.journal?.title ?? "…")
                .font(.system(size: 14, weight: .semibold))
                .foregroundColor(.white)
            if let n = vm.journal?.collaboratorCount, n > 0 {
                Text("· \(n) collaborator\(n == 1 ? "" : "s")")
                    .font(.system(size: 11))
                    .foregroundColor(.secondary)
            }
            Spacer()
            Button { showStylePopover = true } label: {
                Image(systemName: "textformat")
                    .font(.system(size: 11, weight: .medium))
                    .foregroundColor(.white.opacity(0.6))
                    .padding(.horizontal, 6).padding(.vertical, 3)
                    .background(Color.white.opacity(0.05))
                    .cornerRadius(4)
            }
            .buttonStyle(.plain)
            .popover(isPresented: $showStylePopover, arrowEdge: .bottom) {
                JournalStylePopover(journalId: journalId)
            }
            Button {
                showInviteSheet = true
            } label: {
                HStack(spacing: 3) {
                    Image(systemName: "person.badge.plus").font(.system(size: 10))
                    Text("Invite").font(.system(size: 10, weight: .medium))
                }
                .padding(.horizontal, 7).padding(.vertical, 3)
                .background(Color.matcha600.opacity(0.2))
                .foregroundColor(Color.matcha500)
                .cornerRadius(4)
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
    }

    // MARK: - Composer

    private var composer: some View {
        VStack(alignment: .leading, spacing: 6) {
            if !composerOpen {
                Button { composerOpen = true } label: {
                    HStack {
                        Image(systemName: "plus.circle").foregroundColor(.secondary)
                        Text("New entry today…").font(.system(size: 12)).foregroundColor(.secondary)
                        Spacer()
                    }
                    .padding(8)
                    .background(Color.zinc800.opacity(0.4))
                    .cornerRadius(6)
                }
                .buttonStyle(.plain)
            } else {
                HStack {
                    TextField("Title (optional)", text: $composerTitle)
                        .textFieldStyle(.plain)
                        .font(.system(size: 13, weight: .medium))
                        .foregroundColor(.white)
                    DatePicker("", selection: $composerDate, displayedComponents: .date)
                        .labelsHidden()
                        .controlSize(.small)
                }
                JournalEditorToolbar(controller: composerController)
                RichJournalEditor(
                    text: $composerContent,
                    controller: composerController,
                    fontFamily: fontFamily,
                    fontSize: fontSize,
                    lineSpacing: lineSpacing,
                )
                .frame(minHeight: 100, maxHeight: 200)
                .background(Color.zinc800.opacity(0.4))
                .cornerRadius(4)
                HStack {
                    Spacer()
                    Button("Cancel") { resetComposer() }
                        .buttonStyle(.plain)
                        .font(.system(size: 11))
                        .foregroundColor(.secondary)
                    Button {
                        Task { await saveComposer() }
                    } label: {
                        Text("Save").font(.system(size: 11, weight: .semibold))
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(Color.matcha600)
                    .controlSize(.small)
                    .disabled(composerContent.trimmingCharacters(in: .whitespaces).isEmpty)
                    .keyboardShortcut(.return, modifiers: .command)
                }
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 8)
    }

    // MARK: - Timeline

    @ViewBuilder
    private var timeline: some View {
        if vm.isLoading {
            Spacer(); ProgressView().tint(.secondary); Spacer()
        } else if let err = vm.errorMessage {
            VStack(spacing: 6) {
                Spacer()
                Image(systemName: "exclamationmark.triangle").font(.system(size: 22)).foregroundColor(.red)
                Text(err).font(.system(size: 11)).foregroundColor(.secondary)
                Spacer()
            }
        } else if vm.entries.isEmpty {
            VStack(spacing: 6) {
                Spacer()
                Image(systemName: "tray").font(.system(size: 22)).foregroundColor(.secondary)
                Text("No entries yet").font(.system(size: 11)).foregroundColor(.secondary)
                Spacer()
            }
        } else {
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 8) {
                    ForEach(groupedEntries, id: \.0) { date, items in
                        Text(formatDateHeader(date))
                            .font(.system(size: 10, weight: .semibold))
                            .foregroundColor(.secondary)
                            .textCase(.uppercase)
                            .padding(.top, 6)
                        ForEach(items) { entry in
                            entryCard(entry)
                        }
                    }
                }
                .padding(14)
            }
        }
    }

    private func entryCard(_ entry: MWJournalEntry) -> some View {
        let isEditing = editingEntryId == entry.id
        return VStack(alignment: .leading, spacing: 6) {
            HStack {
                if isEditing {
                    TextField("Title", text: $editingTitle)
                        .textFieldStyle(.plain)
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundColor(.white)
                    DatePicker("", selection: $editingDate, displayedComponents: .date)
                        .labelsHidden()
                        .controlSize(.small)
                } else if let t = entry.title, !t.isEmpty {
                    Text(t)
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundColor(.white)
                }
                Spacer()
                Menu {
                    Button("Edit") { beginEdit(entry) }
                    Button("Delete", role: .destructive) { pendingDelete = entry }
                } label: {
                    Image(systemName: "ellipsis")
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundColor(.secondary)
                        .padding(.horizontal, 6)
                }
                .menuStyle(.borderlessButton)
                .menuIndicator(.hidden)
                .fixedSize()
            }
            if isEditing {
                JournalEditorToolbar(controller: editController)
                RichJournalEditor(
                    text: $editingDraft,
                    controller: editController,
                    fontFamily: fontFamily,
                    fontSize: fontSize,
                    lineSpacing: lineSpacing,
                )
                .frame(minHeight: 100, maxHeight: 260)
                .background(Color.zinc800.opacity(0.4))
                .cornerRadius(4)
                HStack {
                    Spacer()
                    Button("Cancel") { editingEntryId = nil }
                        .buttonStyle(.plain)
                        .font(.system(size: 11))
                        .foregroundColor(.secondary)
                    Button("Save") {
                        Task { await commitEdit(entry) }
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(Color.matcha600)
                    .controlSize(.small)
                }
            } else {
                JournalContentView(
                    content: entry.content,
                    fontFamily: fontFamily,
                    fontSize: fontSize,
                    lineSpacing: lineSpacing,
                    onToggleTodo: { idx in
                        Task { await vm.toggleTodo(entry, todoIndex: idx) }
                    },
                )
            }
        }
        .padding(10)
        .background(Color.zinc900.opacity(0.5))
        .cornerRadius(6)
    }

    private var groupedEntries: [(String, [MWJournalEntry])] {
        var seen: [String: [MWJournalEntry]] = [:]
        var order: [String] = []
        for e in vm.entries {
            if seen[e.entryDate] == nil { order.append(e.entryDate) }
            seen[e.entryDate, default: []].append(e)
        }
        return order.map { ($0, seen[$0] ?? []) }
    }

    private func formatDateHeader(_ ymd: String) -> String {
        let inFmt = DateFormatter()
        inFmt.dateFormat = "yyyy-MM-dd"
        guard let d = inFmt.date(from: ymd) else { return ymd }
        let cal = Calendar.current
        if cal.isDateInToday(d) { return "Today" }
        if cal.isDateInYesterday(d) { return "Yesterday" }
        let outFmt = DateFormatter()
        outFmt.dateStyle = .medium
        return outFmt.string(from: d)
    }

    // MARK: - Actions

    private func resetComposer() {
        composerOpen = false
        composerTitle = ""
        composerContent = ""
        composerDate = Date()
    }

    private func saveComposer() async {
        let trimmed = composerContent.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        let dateStr = ymd(composerDate)
        let title = composerTitle.isEmpty ? nil : composerTitle
        await vm.createEntry(title: title, content: trimmed, entryDate: dateStr)
        resetComposer()
    }

    private func beginEdit(_ entry: MWJournalEntry) {
        editingEntryId = entry.id
        editingDraft = entry.content
        editingTitle = entry.title ?? ""
        let inFmt = DateFormatter()
        inFmt.dateFormat = "yyyy-MM-dd"
        editingDate = inFmt.date(from: entry.entryDate) ?? Date()
    }

    private func commitEdit(_ entry: MWJournalEntry) async {
        let title = editingTitle.isEmpty ? nil : editingTitle
        await vm.updateEntry(entry, title: title, content: editingDraft, entryDate: ymd(editingDate))
        editingEntryId = nil
    }

    private func ymd(_ date: Date) -> String {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd"
        return f.string(from: date)
    }
}
