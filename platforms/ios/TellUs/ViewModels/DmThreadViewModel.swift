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
            let sent = try await DmService.shared.send(threadId: threadId, body: trimmed)
            messages.append(sent)
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
                DmThread(id: $0.id, report_id: $0.report_id, counterparty_name: $0.counterparty_name,
                         report_title: $0.report_title, report_number: $0.report_number,
                         review_state: $0.review_state, publish_at: $0.publish_at,
                         blocked: true, unread_count: $0.unread_count,
                         last_message_at: $0.last_message_at, created_at: $0.created_at)
            }
        }
    }

    func unblock() async {
        await withLoad {
            try await DmService.shared.unblock(threadId: threadId)
            thread = thread.map {
                DmThread(id: $0.id, report_id: $0.report_id, counterparty_name: $0.counterparty_name,
                         report_title: $0.report_title, report_number: $0.report_number,
                         review_state: $0.review_state, publish_at: $0.publish_at,
                         blocked: false, unread_count: $0.unread_count,
                         last_message_at: $0.last_message_at, created_at: $0.created_at)
            }
        }
    }

    /// Mirrors web Messages.tsx: opening a thread marks its dm_message
    /// notifications read so the bell badge doesn't keep counting a
    /// conversation the user is actively looking at.
    private func markRelatedNotificationsRead() async {
        guard let items = try? await NotificationsService.shared.list(unreadOnly: true, limit: 100) else { return }
        for item in items where item.kind == "dm_message" && item.reference_id == threadId {
            try? await NotificationsService.shared.markRead(id: item.id)
        }
    }
}
