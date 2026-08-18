import Foundation
import Observation

@MainActor
@Observable
final class SetupMerlinViewModel: LoadableVM {
    let siteId: String
    var isLoading = false
    var error: String?
    var conversationId: String?
    private(set) var messages: [CappeMerlinStoredMessage] = []
    private(set) var stagedActions: [CappeSetupActionEntry] = []
    private(set) var readiness: [String: JSONValue] = [:]
    var draft = ""
    private var task: Task<Void, Never>?

    init(siteId: String) { self.siteId = siteId }

    func load() async {
        await withLoad {
            let conversations = try await MerlinService.shared.setupConversations(siteId: siteId)
            if let first = conversations.first { await open(first.id) }
        }
    }

    func open(_ id: String) async {
        await withLoad {
            let detail = try await MerlinService.shared.setupConversation(id)
            conversationId = id
            messages = detail.messages
            stagedActions = detail.staged_actions ?? []
        }
    }

    func send() async {
        let message = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !message.isEmpty else { return }
        draft = ""
        task = Task { await performSend(message) }
        await task?.value
    }

    func execute(_ action: CappeSetupActionEntry) async {
        guard let conversationId else { return }
        await withLoad {
            let result = try await MerlinService.shared.executeAction(conversationId: conversationId, actionId: action.id)
            upsert(result.action)
            readiness = result.readiness
        }
    }

    func dismiss(_ action: CappeSetupActionEntry) async {
        guard let conversationId else { return }
        await withLoad {
            let detail = try await MerlinService.shared.dismissAction(conversationId: conversationId, actionId: action.id)
            stagedActions = detail.staged_actions ?? []
        }
    }

    private func performSend(_ message: String) async {
        isLoading = true; error = nil
        defer { isLoading = false }
        messages.append(CappeMerlinStoredMessage(
            id: "local-user-\(UUID().uuidString)", role: "user", content: message,
            results: nil, steps: nil, attachments: nil, ops: nil, tier: nil,
            created_at: ISO8601DateFormatter().string(from: Date())
        ))
        do {
            try await MerlinService.shared.setupAgent(siteId: siteId, CappeMerlinSetupRequest(conversation_id: conversationId, message: message)) { [weak self] frame in
                guard let self else { return }
                switch frame {
                case .stagedAction(let action): upsert(action)
                case .result(let result):
                    if let id = result.conversation_id { conversationId = id }
                case .setupResult(let result):
                    if let id = result.conversation_id { conversationId = id }
                    readiness = result.readiness ?? [:]
                    messages.append(CappeMerlinStoredMessage(
                        id: result.message_id ?? "local-assistant-\(UUID().uuidString)",
                        role: "assistant", content: result.message,
                        results: nil, steps: result.steps, attachments: nil,
                        ops: nil, tier: result.tier,
                        created_at: ISO8601DateFormatter().string(from: Date())
                    ))
                case .error(let value): error = value
                default: break
                }
            }
        } catch {
            if !error.isCancellation && self.error == nil { self.error = error.localizedDescription }
        }
    }

    private func upsert(_ action: CappeSetupActionEntry) {
        if let index = stagedActions.firstIndex(where: { $0.id == action.id }) { stagedActions[index] = action }
        else { stagedActions.append(action) }
    }
}
