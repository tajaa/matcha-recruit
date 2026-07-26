import Foundation
import Observation

/// Direct-message conversation list + total unread. DMs are REST-only (not on
/// the channels socket), so this refreshes on appear / pull / poll rather than
/// via live push.
@MainActor
@Observable
final class InboxListViewModel {
    var conversations: [MWInboxConversation] = []
    var isLoading = false
    var errorMessage: String?
    var unreadTotal = 0

    private let service = InboxService.shared

    func load(initial: Bool = false) async {
        if initial { isLoading = true }
        errorMessage = nil
        do {
            conversations = try await service.listConversations()
            unreadTotal = conversations.reduce(0) { $0 + ($1.unreadCount ?? 0) }
        } catch {
            errorMessage = error.localizedDescription
        }
        isLoading = false
    }

    func markConversationRead(_ id: String) {
        guard let i = conversations.firstIndex(where: { $0.id == id }) else { return }
        unreadTotal = max(0, unreadTotal - (conversations[i].unreadCount ?? 0))
        conversations[i].unreadCount = 0
    }
}
