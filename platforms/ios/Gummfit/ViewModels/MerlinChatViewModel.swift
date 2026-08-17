import Foundation
import Observation

@MainActor
@Observable
final class MerlinChatViewModel: LoadableVM {
    var isLoading = false
    var error: String?
    unowned let editor: PageEditorViewModel
    var conversationId: String?
    private(set) var messages: [CappeMerlinStoredMessage] = []
    private(set) var liveSteps: [CappeMerlinStep] = []
    var statusLine: String?
    var draft = ""
    var tier = "auto"
    private var task: Task<Void, Never>?

    init(editor: PageEditorViewModel) { self.editor = editor }

    func load() async {
        await withLoad {
            let conversations = try await MerlinService.shared.conversations(siteId: editor.site.id, pageId: editor.pageId)
            if let first = conversations.first { await open(first.id) }
        }
    }

    func open(_ id: String) async {
        await withLoad {
            let detail = try await MerlinService.shared.conversation(id)
            conversationId = id
            messages = detail.messages
        }
    }

    func cancel() { task?.cancel(); task = nil; isLoading = false }

    func send() async {
        let message = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !message.isEmpty, message.count <= 2000 else { error = "Enter a message up to 2,000 characters."; return }
        draft = ""
        task = Task { await performSend(message) }
        await task?.value
    }

    private func performSend(_ message: String) async {
        isLoading = true; error = nil; liveSteps = []; statusLine = "Thinking…"
        defer { isLoading = false; statusLine = nil }
        let history = messages.suffix(20).map { CappeMerlinHistoryTurn(role: $0.role, content: $0.content, ops_summary: nil) }
        let selectedBlock: String? = editor.selection.flatMap { selection in
            editor.blocks.indices.contains(selection.block) ? editor.blocks[selection.block]._k : nil
        }
        let body = CappeMerlinChatRequest(
            page_id: editor.pageId, conversation_id: conversationId,
            message: message, history: Array(history), blocks: editor.blocks,
            theme: editor.theme, model_tier: tier, selected_block: selectedBlock,
            selection: editor.selection.flatMap(editor.selectionFromPreview), attachments: []
        )
        do {
            try await MerlinService.shared.agent(siteId: editor.site.id, body) { [weak self] frame in
                guard let self else { return }
                switch frame {
                case .status(let value): statusLine = value
                case .step(let step): liveSteps.append(step)
                case .error(let value): error = value
                case .result(let result):
                    if let id = result.conversation_id { conversationId = id }
                    let ops = result.ops.map(MerlinOp.init)
                    let applied = editor.apply(ops: ops)
                    if let id = result.message_id {
                        Task { try? await MerlinService.shared.reportResults(messageId: id, applied.results) }
                    }
                default: break
                }
            }
        } catch {
            if !error.isCancellation { self.error = error.localizedDescription }
        }
    }
}
