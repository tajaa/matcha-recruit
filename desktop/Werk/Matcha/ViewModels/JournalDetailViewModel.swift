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

    private func sortEntries() {
        entries.sort { a, b in
            if a.entryDate != b.entryDate { return a.entryDate > b.entryDate }
            return (a.createdAt ?? "") > (b.createdAt ?? "")
        }
    }
}
