import SwiftUI
import AppKit
import UniformTypeIdentifiers

/// Right-pane journal view. A list of entries (grouped by date) that opens a
/// single entry as a **full page** (Day One style): tap an entry — or "New
/// entry" — and it fills the pane with a title, date and a full-height
/// `RichJournalEditor`; a back button autosaves and returns to the list.
struct JournalDetailView: View {
    let journalId: String
    /// True in a secondary (aux) window — suppresses shared nav/tab writes.
    let isEmbedded: Bool

    @Environment(AppState.self) private var appState
    @State private var vm = JournalDetailViewModel()

    // Page (full-screen entry) state. `openEntry` set = editing an existing
    // entry; `isCreatingEntry` = a new blank page. Both nil/false = list mode.
    @State private var openEntry: MWJournalEntry? = nil
    @State private var isCreatingEntry = false
    @State private var pageTitle = ""
    @State private var pageContent = ""
    @State private var pageDate: Date = Date()
    // Snapshot taken when a page opens, to detect dirty edits for autosave.
    @State private var pageOrigTitle = ""
    @State private var pageOrigContent = ""
    @State private var pageOrigDate = ""

    @State private var showInviteSheet = false
    @State private var showStylePopover = false
    @State private var pendingDelete: MWJournalEntry? = nil
    @StateObject private var pageController = JournalEditorController()

    // Doc-kind (single-document) editing state. A doc-kind journal edits ONE
    // body entry directly — no timeline, no entry-date. `docSeededFor` guards
    // a one-time seed of the editor from the loaded entry so re-renders don't
    // clobber live edits; `docEntry` is a value snapshot used for a safe
    // entry-scoped flush when navigating away.
    @State private var docContent = ""
    @State private var docTitle = ""
    @State private var docOrigContent = ""
    @State private var docOrigTitle = ""
    @State private var docEntry: MWJournalEntry?
    @State private var docSeededFor: String?
    @State private var saveTask: Task<Void, Never>?
    @State private var docReadingMode = false

    // Style preferences keyed by journal — read with @AppStorage so the
    // editor + renderer update as soon as the user changes them.
    @AppStorage private var fontFamily: String
    @AppStorage private var fontSizeRaw: Double
    @AppStorage private var lineSpacingRaw: Double

    init(journalId: String, isEmbedded: Bool = false) {
        self.journalId = journalId
        self.isEmbedded = isEmbedded
        _fontFamily = AppStorage(wrappedValue: "system", "journal.\(journalId).font.family")
        _fontSizeRaw = AppStorage(wrappedValue: 13.0, "journal.\(journalId).font.size")
        _lineSpacingRaw = AppStorage(wrappedValue: 3.0, "journal.\(journalId).line.spacing")
    }

    private var fontSize: CGFloat { CGFloat(fontSizeRaw) }
    private var lineSpacing: CGFloat { CGFloat(lineSpacingRaw) }
    private var inPageMode: Bool { isCreatingEntry || openEntry != nil }

    var body: some View {
        Group {
            if let j = vm.journal {
                if JournalKind.from(j.kind).isDocKind {
                    docEditor
                } else if inPageMode {
                    entryPage
                } else {
                    listView
                }
            } else {
                loadingOrError
            }
        }
        .background(Color.appBackground)
        .task(id: journalId) {
            await vm.load(id: journalId)
            if vm.kind.isDocKind { await vm.ensureBodyEntry() }
            syncDocFromVM()
            if !isEmbedded {
                appState.setActiveContext(WorkTab(kind: .journal, entityId: journalId,
                                                  title: vm.journal?.title ?? "Journal"))
            }
        }
        .onAppear { wireUploadCallbacks() }
        .onChange(of: journalId) { _, _ in
            flushLeavingDoc()      // persist the doc we're leaving (entry-scoped, safe)
            docSeededFor = nil     // force a reseed for the incoming doc
            wireUploadCallbacks()
        }
        .onChange(of: vm.bodyEntry?.id) { _, _ in syncDocFromVM() }
        .onDisappear { flushLeavingDoc() }
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
                // If the open page is this entry, leave the page without saving.
                if openEntry?.id == target.id {
                    openEntry = nil
                    isCreatingEntry = false
                }
                Task { await vm.deleteEntry(target) }
            }
            Button("Cancel", role: .cancel) { pendingDelete = nil }
        } message: { _ in Text("This cannot be undone.") }
    }

    /// Wire the editor's image-upload path to the VM. Re-wire when journalId
    /// changes so uploads target the right journal.
    private func wireUploadCallbacks() {
        pageController.onUploadImage = { [vm] data, name, mime in
            await vm.uploadImage(data: data, filename: name, mimeType: mime)
        }
    }

    // MARK: - List mode

    private var listView: some View {
        VStack(spacing: 0) {
            header
            Divider().opacity(0.2)
            newEntryBar
            Divider().opacity(0.2)
            timeline
        }
    }

    private var header: some View {
        HStack(spacing: 8) {
            Image(systemName: vm.journal?.icon ?? "book")
                .font(.system(size: 14))
                .foregroundColor(appState.themeAccent)
            Text(vm.journal?.title ?? "…")
                .font(.system(size: 14, weight: .semibold))
                .foregroundColor(appState.themeText)
            if let n = vm.journal?.collaboratorCount, n > 0 {
                Text("· \(n) collaborator\(n == 1 ? "" : "s")")
                    .font(.system(size: 11))
                    .foregroundColor(appState.themeTextSecondary)
            }
            Spacer()
            Button { showStylePopover = true } label: {
                Image(systemName: "textformat")
                    .font(.system(size: 11, weight: .medium))
                    .foregroundColor(appState.themeText.opacity(0.6))
                    .padding(.horizontal, 6).padding(.vertical, 3)
                    .background(appState.themeText.opacity(0.05))
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
                .background(appState.themeAccentDark.opacity(0.2))
                .foregroundColor(appState.themeAccent)
                .cornerRadius(4)
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
    }

    private var newEntryBar: some View {
        Button { startNew() } label: {
            HStack(spacing: 6) {
                Image(systemName: "square.and.pencil")
                    .font(.system(size: 12))
                    .foregroundColor(appState.themeAccent)
                Text("New entry")
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(appState.themeAccent)
                Spacer()
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 8)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    @ViewBuilder
    private var timeline: some View {
        if vm.isLoading {
            Spacer(); ProgressView().tint(.secondary); Spacer()
        } else if let err = vm.errorMessage {
            VStack(spacing: 10) {
                Spacer()
                Image(systemName: "exclamationmark.triangle").font(.system(size: 22)).foregroundColor(.red)
                Text(err).font(.system(size: 11)).foregroundColor(appState.themeTextSecondary).multilineTextAlignment(.center).padding(.horizontal, 16)
                Button {
                    Task { await vm.refresh() }
                } label: {
                    Text("Try again").font(.system(size: 11, weight: .medium))
                }
                .buttonStyle(.borderedProminent)
                .tint(appState.themeAccent)
                .controlSize(.small)
                Spacer()
            }
        } else if vm.entries.isEmpty {
            VStack(spacing: 6) {
                Spacer()
                Image(systemName: "tray").font(.system(size: 22)).foregroundColor(appState.themeTextSecondary)
                Text("No entries yet — tap “New entry”.").font(.system(size: 11)).foregroundColor(appState.themeTextSecondary)
                Spacer()
            }
        } else {
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 8) {
                    ForEach(groupedEntries, id: \.0) { date, items in
                        Text(formatDateHeader(date))
                            .font(.system(size: 10, weight: .semibold))
                            .foregroundColor(appState.themeTextSecondary)
                            .textCase(.uppercase)
                            .padding(.top, 6)
                        ForEach(items) { entry in
                            entryRow(entry)
                        }
                    }
                }
                .padding(14)
            }
        }
    }

    /// Compact, tappable list row — opens the entry as a full page.
    private func entryRow(_ entry: MWJournalEntry) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            HStack(alignment: .top) {
                Text((entry.title?.isEmpty == false) ? entry.title! : "Untitled")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundColor(appState.themeText)
                    .lineLimit(1)
                Spacer()
                Menu {
                    Button("Open") { openExisting(entry) }
                    Button("Delete", role: .destructive) { pendingDelete = entry }
                } label: {
                    Image(systemName: "ellipsis")
                        .font(.system(size: 11, weight: .semibold))
                        .foregroundColor(appState.themeTextSecondary)
                        .padding(.horizontal, 6)
                }
                .menuStyle(.borderlessButton)
                .menuIndicator(.hidden)
                .fixedSize()
            }
            let preview = previewText(entry.content)
            if !preview.isEmpty {
                Text(preview)
                    .font(.system(size: 11))
                    .foregroundColor(appState.themeTextSecondary)
                    .lineLimit(2)
                    .multilineTextAlignment(.leading)
            }
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(appState.themeCard.opacity(0.5))
        .cornerRadius(6)
        .contentShape(Rectangle())
        .onTapGesture { openExisting(entry) }
    }

    // MARK: - Page mode (full entry)

    private var entryPage: some View {
        VStack(spacing: 0) {
            HStack(spacing: 8) {
                Button { Task { await closePageSaving() } } label: {
                    HStack(spacing: 3) {
                        Image(systemName: "chevron.left").font(.system(size: 11, weight: .semibold))
                        Text(vm.journal?.title ?? "Journal").font(.system(size: 12, weight: .medium))
                    }
                    .foregroundColor(appState.themeAccent)
                }
                .buttonStyle(.plain)
                .keyboardShortcut("[", modifiers: .command)
                Spacer()
                if let entry = openEntry {
                    Button(role: .destructive) { pendingDelete = entry } label: {
                        Image(systemName: "trash").font(.system(size: 12))
                    }
                    .buttonStyle(.plain)
                    .foregroundColor(.red.opacity(0.8))
                    .help("Delete entry")
                }
            }
            .padding(.horizontal, 14)
            .padding(.vertical, 10)
            Divider().opacity(0.2)

            HStack {
                TextField("Title (optional)", text: $pageTitle)
                    .textFieldStyle(.plain)
                    .font(.system(size: 16, weight: .semibold))
                    .foregroundColor(appState.themeText)
                DatePicker("", selection: $pageDate, displayedComponents: .date)
                    .labelsHidden()
                    .controlSize(.small)
            }
            .padding(.horizontal, 14)
            .padding(.top, 10)
            .padding(.bottom, 6)

            JournalEditorToolbar(controller: pageController)
                .padding(.horizontal, 14)

            RichJournalEditor(
                text: $pageContent,
                controller: pageController,
                fontFamily: fontFamily,
                fontSize: fontSize,
                lineSpacing: lineSpacing,
            )
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .padding(.horizontal, 14)
            .padding(.bottom, 14)
        }
    }

    // MARK: - Doc mode (single-document kinds: note/blog/novel/todo/screenplay)

    /// Honor an explicit user override; otherwise default by kind (novel/blog →
    /// serif). Screenplay gets its own editor later (Part B).
    private var effectiveFontFamily: String {
        fontFamily == "system" ? vm.kind.defaultFontFamily : fontFamily
    }

    private var docEditor: some View {
        VStack(spacing: 0) {
            docHeader
            Divider().opacity(0.2)
            if vm.kind.usesScreenplayEditor {
                ScreenplayDocEditor(
                    text: $docContent,
                    fontSize: fontSize,
                    textColor: appState.themeText,
                )
            } else if docReadingMode {
                ScrollView {
                    JournalContentView(
                        content: docContent,
                        fontFamily: effectiveFontFamily,
                        fontSize: fontSize,
                        lineSpacing: lineSpacing,
                        baseColor: appState.themeText,
                    )
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(16)
                }
            } else {
                JournalEditorToolbar(controller: pageController)
                    .padding(.horizontal, 14)
                    .padding(.top, 6)
                RichJournalEditor(
                    text: $docContent,
                    controller: pageController,
                    fontFamily: effectiveFontFamily,
                    fontSize: fontSize,
                    lineSpacing: lineSpacing,
                    slashBlocks: vm.kind.slashBlocks,
                    textColor: NSColor(appState.themeText),
                )
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .padding(.horizontal, 14)
                .padding(.bottom, 14)
            }
        }
        .onChange(of: docContent) { _, _ in scheduleSave() }
        .onChange(of: docTitle) { _, _ in scheduleSave() }
    }

    private var docHeader: some View {
        HStack(spacing: 8) {
            Image(systemName: vm.journal?.icon ?? vm.kind.icon)
                .font(.system(size: 14))
                .foregroundColor(appState.themeAccent)
            TextField("Untitled", text: $docTitle)
                .textFieldStyle(.plain)
                .font(.system(size: 15, weight: .semibold))
                .foregroundColor(appState.themeText)
                .onSubmit { Task { await saveDocIfDirty() } }
            Spacer()
            if let n = vm.journal?.collaboratorCount, n > 0 {
                Text("\(n) collaborator\(n == 1 ? "" : "s")")
                    .font(.system(size: 11))
                    .foregroundColor(appState.themeTextSecondary)
            }
            if !vm.kind.usesScreenplayEditor {
                Button { docReadingMode.toggle() } label: {
                    Image(systemName: docReadingMode ? "pencil" : "eye")
                        .font(.system(size: 11, weight: .medium))
                        .foregroundColor(appState.themeText.opacity(0.6))
                        .padding(.horizontal, 6).padding(.vertical, 3)
                        .background(appState.themeText.opacity(0.05))
                        .cornerRadius(4)
                }
                .buttonStyle(.plain)
                .help(docReadingMode ? "Edit" : "Reading mode")
            }
            Menu {
                if vm.kind.usesScreenplayEditor {
                    Button("Copy as Fountain") { copyFountain() }
                    Divider()
                    Button("Export .fountain…") { exportFountain() }
                    Button("Export PDF…") { exportScreenplayPDF() }
                } else {
                    Button("Copy as Markdown") { copyDoc(asHTML: false) }
                    Button("Copy as HTML") { copyDoc(asHTML: true) }
                    Divider()
                    Button("Export Markdown…") { exportDoc(asHTML: false) }
                    Button("Export HTML…") { exportDoc(asHTML: true) }
                }
            } label: {
                Image(systemName: "square.and.arrow.up")
                    .font(.system(size: 11, weight: .medium))
                    .foregroundColor(appState.themeText.opacity(0.6))
                    .padding(.horizontal, 6).padding(.vertical, 3)
                    .background(appState.themeText.opacity(0.05))
                    .cornerRadius(4)
            }
            .menuStyle(.borderlessButton)
            .menuIndicator(.hidden)
            .fixedSize()
            .help("Export / copy")
            Button { showStylePopover = true } label: {
                Image(systemName: "textformat")
                    .font(.system(size: 11, weight: .medium))
                    .foregroundColor(appState.themeText.opacity(0.6))
                    .padding(.horizontal, 6).padding(.vertical, 3)
                    .background(appState.themeText.opacity(0.05))
                    .cornerRadius(4)
            }
            .buttonStyle(.plain)
            .popover(isPresented: $showStylePopover, arrowEdge: .bottom) {
                JournalStylePopover(journalId: journalId)
            }
            Button { showInviteSheet = true } label: {
                HStack(spacing: 3) {
                    Image(systemName: "person.badge.plus").font(.system(size: 10))
                    Text("Invite").font(.system(size: 10, weight: .medium))
                }
                .padding(.horizontal, 7).padding(.vertical, 3)
                .background(appState.themeAccentDark.opacity(0.2))
                .foregroundColor(appState.themeAccent)
                .cornerRadius(4)
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
    }

    @ViewBuilder
    private var loadingOrError: some View {
        if let err = vm.errorMessage {
            VStack(spacing: 10) {
                Spacer()
                Image(systemName: "exclamationmark.triangle").font(.system(size: 22)).foregroundColor(.red)
                Text(err).font(.system(size: 11)).foregroundColor(appState.themeTextSecondary)
                    .multilineTextAlignment(.center).padding(.horizontal, 16)
                Button { Task { await vm.refresh() } } label: {
                    Text("Try again").font(.system(size: 11, weight: .medium))
                }
                .buttonStyle(.borderedProminent).tint(appState.themeAccent).controlSize(.small)
                Spacer()
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else {
            VStack { Spacer(); ProgressView().tint(.secondary); Spacer() }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }

    /// Seed the editor from the loaded body entry exactly once per journal so
    /// re-renders never clobber what the user is typing.
    private func syncDocFromVM() {
        guard vm.kind.isDocKind, let entry = vm.bodyEntry else { return }
        guard docSeededFor != journalId else { return }
        docContent = entry.content
        docOrigContent = entry.content
        docTitle = vm.journal?.title ?? ""
        docOrigTitle = docTitle
        docEntry = entry
        docSeededFor = journalId
    }

    /// Debounced autosave — only the latest edit wins.
    private func scheduleSave() {
        saveTask?.cancel()
        saveTask = Task {
            try? await Task.sleep(for: .milliseconds(800))
            if Task.isCancelled { return }
            await saveDocIfDirty()
        }
    }

    private func saveDocIfDirty() async {
        // Use the captured body-entry snapshot (not vm.bodyEntry): if navigation
        // raced ahead and the VM already reloaded a different journal, the
        // content still lands in the right entry (updateJournalEntry is
        // entry-scoped). Title goes through the loadedId-scoped updateJournalMeta,
        // so only persist it while we're still on this document.
        guard let entry = docEntry else { return }
        if docContent != docOrigContent {
            await vm.updateEntry(entry, title: entry.title, content: docContent, entryDate: entry.entryDate)
            docOrigContent = docContent
        }
        let titleTrimmed = docTitle.trimmingCharacters(in: .whitespaces)
        if !titleTrimmed.isEmpty, titleTrimmed != docOrigTitle, vm.loadedId == entry.journalId {
            await vm.updateJournalMeta(title: titleTrimmed)
            docOrigTitle = titleTrimmed
            appState.journalsListGeneration &+= 1   // relabel the sidebar row
        }
    }

    /// Flush the document we're leaving. Entry-scoped (targets the captured
    /// entry's own journal), so it's safe even after the VM has begun loading a
    /// different journal. Title edits are persisted on-page via debounce/onSubmit.
    private func flushLeavingDoc() {
        saveTask?.cancel()
        guard let entry = docEntry, docContent != docOrigContent else { return }
        let content = docContent
        docOrigContent = content
        Task {
            _ = try? await MatchaWorkService.shared.updateJournalEntry(
                entryId: entry.id, journalId: entry.journalId,
                title: entry.title, content: content, entryDate: entry.entryDate,
            )
        }
    }

    // MARK: - Export / copy

    private func copyDoc(asHTML: Bool) {
        let pb = NSPasteboard.general
        pb.clearContents()
        if asHTML {
            let html = JournalMarkdownExport.html(docContent)
            pb.setString(html, forType: .html)
            pb.setString(html, forType: .string)
        } else {
            pb.setString(JournalMarkdownExport.markdown(docContent), forType: .string)
        }
    }

    private var docExportBaseName: String {
        docTitle.trimmingCharacters(in: .whitespaces).isEmpty
            ? (vm.journal?.title ?? "document") : docTitle
    }

    private func exportDoc(asHTML: Bool) {
        let base = docExportBaseName
        let panel = NSSavePanel()
        panel.nameFieldStringValue = base + (asHTML ? ".html" : ".md")
        panel.allowedContentTypes = asHTML
            ? [.html]
            : [UTType(filenameExtension: "md") ?? .plainText]
        guard panel.runModal() == .OK, let url = panel.url else { return }
        let text = asHTML
            ? JournalMarkdownExport.htmlDocument(docContent, title: base)
            : JournalMarkdownExport.markdown(docContent)
        try? text.write(to: url, atomically: true, encoding: .utf8)
    }

    // MARK: - Screenplay export (Fountain + PDF)

    private func copyFountain() {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(docContent, forType: .string)
    }

    private func exportFountain() {
        let panel = NSSavePanel()
        panel.nameFieldStringValue = docExportBaseName + ".fountain"
        panel.allowedContentTypes = [UTType(filenameExtension: "fountain") ?? .plainText]
        guard panel.runModal() == .OK, let url = panel.url else { return }
        try? docContent.write(to: url, atomically: true, encoding: .utf8)
    }

    private func exportScreenplayPDF() {
        guard let data = ScreenplayPDF.render(FountainParser.parse(docContent)) else { return }
        let panel = NSSavePanel()
        panel.nameFieldStringValue = docExportBaseName + ".pdf"
        panel.allowedContentTypes = [.pdf]
        guard panel.runModal() == .OK, let url = panel.url else { return }
        try? data.write(to: url)
    }

    // MARK: - Grouping + formatting

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

    /// One-line preview of markdown content for the list row.
    private func previewText(_ content: String) -> String {
        content
            .replacingOccurrences(of: "\n", with: " ")
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }

    // MARK: - Actions

    private func startNew() {
        openEntry = nil
        pageTitle = ""; pageContent = ""; pageDate = Date()
        pageOrigTitle = ""; pageOrigContent = ""; pageOrigDate = ymd(Date())
        isCreatingEntry = true
    }

    private func openExisting(_ entry: MWJournalEntry) {
        isCreatingEntry = false
        pageTitle = entry.title ?? ""
        pageContent = entry.content
        let inFmt = DateFormatter(); inFmt.dateFormat = "yyyy-MM-dd"
        pageDate = inFmt.date(from: entry.entryDate) ?? Date()
        pageOrigTitle = entry.title ?? ""
        pageOrigContent = entry.content
        pageOrigDate = entry.entryDate
        openEntry = entry
    }

    /// Autosave on exit (like a journaling app) — only writes when dirty.
    private func closePageSaving() async {
        await savePageIfDirty()
        openEntry = nil
        isCreatingEntry = false
    }

    private func savePageIfDirty() async {
        let dateStr = ymd(pageDate)
        let title = pageTitle.isEmpty ? nil : pageTitle
        if let entry = openEntry {
            let changed = pageContent != pageOrigContent
                || pageTitle != pageOrigTitle
                || dateStr != pageOrigDate
            if changed {
                await vm.updateEntry(entry, title: title, content: pageContent, entryDate: dateStr)
            }
        } else if isCreatingEntry {
            guard !pageContent.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
            await vm.createEntry(title: title, content: pageContent, entryDate: dateStr)
        }
    }

    private func ymd(_ date: Date) -> String {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd"
        return f.string(from: date)
    }
}
