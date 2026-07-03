import Foundation

/// Owns the loaded journal + entries for the right-pane detail view. Keeps
/// the view simple — the VM holds all async work and surface error state.
@MainActor
@Observable
final class JournalDetailViewModel {
    var journal: MWJournal?
    var entries: [MWJournalEntry] = []
    var isLoading: Bool = false
    var errorMessage: String?
    /// Last-loaded id so reload tasks can short-circuit when navigation
    /// switches to a different journal mid-flight.
    private(set) var loadedId: String?

    func load(id: String) async {
        loadedId = id
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }
        do {
            async let journalCall = MatchaWorkService.shared.getJournal(id: id)
            async let entriesCall = MatchaWorkService.shared.listJournalEntries(journalId: id)
            let (j, e) = try await (journalCall, entriesCall)
            // Guard against a navigation switch that happened mid-fetch.
            guard loadedId == id else { return }
            journal = j
            entries = e
        } catch {
            errorMessage = "Couldn't load journal: \(error.localizedDescription)"
        }
    }

    func refresh() async {
        guard let id = loadedId else { return }
        await load(id: id)
    }

    // MARK: - Single-document model

    /// The journal's kind, derived from the loaded record (note by default).
    var kind: JournalKind { JournalKind.from(journal?.kind) }

    /// Every journal is a single document now, so its body is the one
    /// `mw_journal_entries` row — `entries.first`.
    var bodyEntry: MWJournalEntry? { entries.first }

    /// Journals open straight into a single editor. Most kinds seed a starter
    /// entry on the backend at create time, but `note` (and any pre-seed
    /// journals) can be empty — lazily create one body entry so the editor
    /// always has something to bind to.
    func ensureBodyEntry() async {
        guard let id = loadedId, journal != nil else { return }
        guard entries.isEmpty else { return }
        do {
            let entry = try await MatchaWorkService.shared.createJournalEntry(
                journalId: id, title: nil, content: "", entryDate: nil,
            )
            guard loadedId == id else { return }   // navigation switched mid-flight
            entries = [entry]
        } catch {
            errorMessage = "Couldn't initialize document: \(error.localizedDescription)"
        }
    }

    func createEntry(title: String?, content: String, entryDate: String?) async {
        guard let id = loadedId else { return }
        errorMessage = nil
        do {
            let entry = try await MatchaWorkService.shared.createJournalEntry(
                journalId: id, title: title, content: content, entryDate: entryDate,
            )
            // Insert at top of list since entries sort by date desc.
            entries.insert(entry, at: 0)
            sortEntries()
        } catch {
            errorMessage = "Couldn't save entry: \(error.localizedDescription)"
        }
    }

    func updateEntry(_ entry: MWJournalEntry, title: String?, content: String, entryDate: String?) async {
        errorMessage = nil
        do {
            let updated = try await MatchaWorkService.shared.updateJournalEntry(
                entryId: entry.id, journalId: entry.journalId,
                title: title, content: content, entryDate: entryDate,
            )
            if let idx = entries.firstIndex(where: { $0.id == entry.id }) {
                entries[idx] = updated
            }
            sortEntries()
        } catch {
            errorMessage = "Couldn't update entry: \(error.localizedDescription)"
        }
    }

    func deleteEntry(_ entry: MWJournalEntry) async {
        errorMessage = nil
        do {
            try await MatchaWorkService.shared.deleteJournalEntry(
                entryId: entry.id, journalId: entry.journalId,
            )
            entries.removeAll { $0.id == entry.id }
        } catch {
            errorMessage = "Couldn't delete entry: \(error.localizedDescription)"
        }
    }

    func updateJournalMeta(
        title: String? = nil, description: String? = nil,
        color: String? = nil, icon: String? = nil
    ) async {
        guard let id = loadedId else { return }
        errorMessage = nil
        do {
            journal = try await MatchaWorkService.shared.updateJournal(
                id: id, title: title, description: description, color: color, icon: icon,
            )
        } catch {
            errorMessage = "Couldn't update journal: \(error.localizedDescription)"
        }
    }

    /// Flip the Nth `- [ ]` ↔ `- [x]` checkbox within an entry's content
    /// and persist. `todoIndex` is the order of the todo across all lines.
    func toggleTodo(_ entry: MWJournalEntry, todoIndex: Int) async {
        let lines = entry.content.components(separatedBy: "\n")
        var newLines = lines
        var seen = 0
        for i in 0..<lines.count {
            let trimmed = lines[i].trimmingCharacters(in: .whitespaces)
            let unchecked = trimmed.hasPrefix("- [ ]") || trimmed.hasPrefix("* [ ]")
            let checked = trimmed.hasPrefix("- [x]") || trimmed.hasPrefix("- [X]")
                || trimmed.hasPrefix("* [x]") || trimmed.hasPrefix("* [X]")
            guard unchecked || checked else { continue }
            if seen == todoIndex {
                if unchecked, let r = lines[i].range(of: "[ ]") {
                    newLines[i] = lines[i].replacingCharacters(in: r, with: "[x]")
                } else if let r = lines[i].range(of: "[x]") ?? lines[i].range(of: "[X]") {
                    newLines[i] = lines[i].replacingCharacters(in: r, with: "[ ]")
                }
                break
            }
            seen += 1
        }
        let newContent = newLines.joined(separator: "\n")
        guard newContent != entry.content else { return }
        await updateEntry(entry, title: entry.title, content: newContent, entryDate: entry.entryDate)
    }

    /// Upload an image to the current journal. Returns the public URL on
    /// success; sets `errorMessage` and returns nil on failure.
    func uploadImage(data: Data, filename: String, mimeType: String) async -> String? {
        guard let id = loadedId else { return nil }
        do {
            return try await MatchaWorkService.shared.uploadJournalImage(
                journalId: id, data: data, filename: filename, mimeType: mimeType,
            )
        } catch {
            errorMessage = "Image upload failed: \(error.localizedDescription)"
            return nil
        }
    }

    private func sortEntries() {
        entries.sort { a, b in
            if a.entryDate != b.entryDate { return a.entryDate > b.entryDate }
            return (a.createdAt ?? "") > (b.createdAt ?? "")
        }
    }
}
