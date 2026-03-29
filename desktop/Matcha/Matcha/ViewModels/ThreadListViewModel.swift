import Foundation

@Observable
class ThreadListViewModel {
    var threads: [MWThread] = []
    var filterStatus: String? = nil
    var isLoading = false
    var errorMessage: String?
    var showNewThread = false

    private let service = MatchaWorkService.shared

    private func sortThreads(_ rows: [MWThread]) -> [MWThread] {
        rows.sorted { lhs, rhs in
            if lhs.isPinned != rhs.isPinned {
                return lhs.isPinned && !rhs.isPinned
            }
            let lhsDate = parseMWDate(lhs.lastActivityAt) ?? .distantPast
            let rhsDate = parseMWDate(rhs.lastActivityAt) ?? .distantPast
            return lhsDate > rhsDate
        }
    }

    var filteredThreads: [MWThread] {
        guard let filter = filterStatus, !filter.isEmpty else { return threads }
        return threads.filter { $0.status == filter }
    }

    func loadThreads() async {
        isLoading = true
        errorMessage = nil
        do {
            let loaded = try await service.listThreads(status: filterStatus)
            await MainActor.run {
                threads = sortThreads(loaded)
                isLoading = false
            }
        } catch {
            await MainActor.run {
                errorMessage = error.localizedDescription
                isLoading = false
            }
        }
    }

    func createThread(title: String?, initialMessage: String? = nil) async -> MWThread? {
        do {
            let thread = try await service.createThread(
                title: title,
                initialMessage: initialMessage
            )
            await MainActor.run {
                threads = sortThreads([thread] + threads.filter { $0.id != thread.id })
            }
            return thread
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
            return nil
        }
    }

    func togglePin(thread: MWThread) async {
        let newPinned = !thread.isPinned
        do {
            let updated = try await service.setPinned(id: thread.id, pinned: newPinned)
            await MainActor.run {
                threads = sortThreads(threads.map { $0.id == thread.id ? updated : $0 })
            }
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    func deleteThread(thread: MWThread) async {
        do {
            try await service.deleteThread(id: thread.id)
            await MainActor.run {
                threads.removeAll { $0.id == thread.id }
            }
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }

    func archiveThread(thread: MWThread) async {
        do {
            try await service.archiveThread(id: thread.id)
            await MainActor.run {
                threads.removeAll { $0.id == thread.id }
            }
        } catch {
            await MainActor.run { errorMessage = error.localizedDescription }
        }
    }
}
