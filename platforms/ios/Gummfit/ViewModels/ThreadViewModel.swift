import Foundation
import Observation

@MainActor
@Observable
final class ThreadViewModel: LoadableVM {
    var thread: CappeThreadDetail?
    var isLoading = false
    var isSending = false
    var error: String?

    /// Marks the thread read server-side as a side effect (messages.py:86-87).
    func load(siteId: String, threadId: String) async {
        await withLoad {
            self.thread = try await MessagesService.shared.getThread(siteId: siteId, threadId: threadId)
        }
    }

    func reply(siteId: String, body: String) async {
        guard let threadId = thread?.id, !body.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
        isSending = true
        error = nil
        defer { isSending = false }
        do {
            let message = try await MessagesService.shared.reply(siteId: siteId, threadId: threadId, body: body)
            thread?.messages.append(message)
        } catch {
            if error.isCancellation { return }
            self.error = error.localizedDescription
        }
    }

    func close(siteId: String) async {
        guard let threadId = thread?.id else { return }
        do {
            let updated = try await MessagesService.shared.close(siteId: siteId, threadId: threadId)
            thread?.status = updated.status
        } catch {
            if error.isCancellation { return }
            self.error = error.localizedDescription
        }
    }
}
