import Foundation
import Observation

@MainActor
@Observable
final class DmThreadViewModel: LoadableVM {
    let threadId: String
    var thread: DmThread?
    var messages: [DmMessage] = []
    var isLoading = false
    var error: String?
    var isSending = false
    private var pendingClientMessageID: String?
    private var pollingTask: Task<Void, Never>?

    init(thread: DmThread) {
        self.threadId = thread.id
        self.thread = thread
    }

    init(threadId: String) {
        self.threadId = threadId
    }

    func load() async {
        await withLoad {
            // No single-thread GET exists server-side — when this VM was
            // constructed from a bare id (e.g. MyReviewDetailView's
            // dm_thread_id link, not a MessagesListView row), resolve
            // `thread` from the list so blocked-state and the title are
            // correct instead of silently staying nil forever.
            if thread == nil {
                thread = try await DmService.shared.threads().first { $0.id == threadId }
            }
            messages = try await DmService.shared.messages(threadId: threadId)
        }
        await markRelatedNotificationsRead()
    }

    func send(_ body: String) async {
        let trimmed = body.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        isSending = true; defer { isSending = false }
        do {
            let clientMessageID = pendingClientMessageID ?? UUID().uuidString
            pendingClientMessageID = clientMessageID
            let sent = try await DmService.shared.send(threadId: threadId, body: trimmed, clientMessageId: clientMessageID)
            messages.append(sent)
            pendingClientMessageID = nil
            error = nil
        } catch {
            if error.isCancellation { return }
            self.error = error.localizedDescription
        }
    }

    func block() async {
        await withLoad {
            try await DmService.shared.block(threadId: threadId)
            thread = thread.map {
                $0.with(blocked: true)
            }
        }
    }

    func unblock() async {
        await withLoad {
            try await DmService.shared.unblock(threadId: threadId)
            thread = thread.map {
                $0.with(blocked: false)
            }
        }
    }

    func take() async {
        await withLoad {
            thread = try await DmService.shared.take(threadId: threadId)
        }
    }

    func assign(to memberID: String?) async {
        await withLoad {
            thread = try await DmService.shared.assign(threadId: threadId, memberID: memberID)
        }
    }

    func close() async {
        await withLoad {
            thread = try await DmService.shared.close(threadId: threadId)
        }
    }

    func startPolling() {
        guard pollingTask == nil else { return }
        pollingTask = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(5))
                guard !Task.isCancelled, let self else { return }
                await self.pollDelta()
            }
        }
    }

    func stopPolling() {
        pollingTask?.cancel()
        pollingTask = nil
    }

    private func pollDelta() async {
        do {
            let incoming = try await DmService.shared.messages(threadId: threadId, after: messages.last?.id)
            let known = Set(messages.map(\.id))
            messages.append(contentsOf: incoming.filter { !known.contains($0.id) })
            error = nil
        } catch {
            if !error.isCancellation { self.error = error.localizedDescription }
        }
    }

    /// Mirrors web Messages.tsx: opening a thread marks its dm_message
    /// notifications read so the bell badge doesn't keep counting a
    /// conversation the user is actively looking at.
    private func markRelatedNotificationsRead() async {
        guard let items = try? await NotificationsService.shared.list(unreadOnly: true, limit: 100) else { return }
        for item in items where ["dm_message", "dm_assignment"].contains(item.kind) && item.reference_id == threadId {
            try? await NotificationsService.shared.markRead(id: item.id)
        }
    }

    deinit { pollingTask?.cancel() }
}
