import Foundation
import Observation

struct FlyerAssistantMessage: Identifiable, Equatable {
    enum Role: String { case user, assistant }

    let id = UUID()
    let role: Role
    let content: String
    let results: [FlyerOpResult]
    let rejected: [FlyerAiRejection]
}

@MainActor
@Observable
final class FlyerAssistantViewModel {
    var messages: [FlyerAssistantMessage] = []
    var ideas: [FlyerIdea] = []
    var isSending = false
    var isLoadingIdeas = false
    var error: String?

    private var history: [FlyerAiHistoryTurn] = []

    func send(
        campaignID: String,
        design: FlyerDesign,
        message rawMessage: String,
        selection: FlyerAiSelection?
    ) async -> FlyerDesign? {
        let message = rawMessage.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !message.isEmpty, !isSending else { return nil }
        isSending = true
        error = nil
        messages.append(FlyerAssistantMessage(role: .user, content: message, results: [], rejected: []))
        defer { isSending = false }

        do {
            let response = try await FlyerAiService.shared.assist(
                campaignID: campaignID,
                request: FlyerAssistRequest(
                    message: message,
                    design: design,
                    history: Array(history.suffix(20)),
                    selection: selection
                )
            )
            let summary = response.results.filter(\.ok).map(\.summary).joined(separator: "; ")
            history.append(FlyerAiHistoryTurn(role: "user", content: message, ops_summary: nil))
            history.append(FlyerAiHistoryTurn(
                role: "assistant",
                content: response.message,
                ops_summary: summary.isEmpty ? nil : String(summary.prefix(2_000))
            ))
            messages.append(FlyerAssistantMessage(
                role: .assistant,
                content: response.message,
                results: response.results,
                rejected: response.rejected
            ))
            return response.design
        } catch {
            if !error.isCancellation { self.error = error.localizedDescription }
            return nil
        }
    }

    func loadIdeas(campaignID: String) async {
        guard !isLoadingIdeas else { return }
        isLoadingIdeas = true
        error = nil
        defer { isLoadingIdeas = false }
        do {
            ideas = try await FlyerAiService.shared.ideas(campaignID: campaignID).ideas
        } catch {
            if !error.isCancellation { self.error = error.localizedDescription }
        }
    }

    func applyIdea(_ idea: FlyerIdea) -> FlyerDesign {
        history.append(FlyerAiHistoryTurn(
            role: "assistant",
            content: "Applied the \(idea.label) layout.",
            ops_summary: "Rebuilt the flyer"
        ))
        messages.append(FlyerAssistantMessage(
            role: .assistant,
            content: "Applied the \(idea.label) layout.",
            results: [],
            rejected: []
        ))
        return idea.design
    }
}
