import Foundation

/// Espresso Tasks (`/matcha-work/agent-tasks/*`): the person's background
/// tasks, what each found, follow-ups, and the forms Espresso asks in chat.
@MainActor
final class AgentTaskService {
    static let shared = AgentTaskService()
    private let client = APIClient.shared
    private let basePath = "/matcha-work/agent-tasks"

    func list() async throws -> AgentTaskList {
        try await client.request(method: "GET", path: basePath)
    }

    /// The sidebar row's counts: running, waiting for the person, finished unseen.
    func summary() async throws -> AgentTasksSummary {
        try await client.request(method: "GET", path: "\(basePath)/summary")
    }

    /// Opening a finished task marks it seen.
    func detail(_ taskId: String) async throws -> AgentTaskDetail {
        try await client.request(method: "GET", path: "\(basePath)/\(taskId)")
    }

    /// Cheap to poll; the server also restarts a stalled task when asked.
    func status(_ taskId: String) async throws -> AgentTaskStatus {
        try await client.request(method: "GET", path: "\(basePath)/\(taskId)/status")
    }

    /// One finding, with the quote and page behind each fact.
    func item(_ taskId: String, _ itemId: String) async throws -> AgentTaskItem {
        try await client.request(method: "GET", path: "\(basePath)/\(taskId)/items/\(itemId)")
    }

    func updateItem(_ taskId: String, _ itemId: String, state: String? = nil, notes: String? = nil) async throws -> AgentTaskItem {
        try await client.request(method: "PATCH", path: "\(basePath)/\(taskId)/items/\(itemId)",
                                 body: AgentTaskItemPatch(userState: state, notes: notes))
    }

    /// Refine (free), search more (1 unit) or make a document (free). The
    /// request id makes a retried tap the same round.
    func startRound(_ taskId: String, kind: String, directive: String = "", itemIds: [String] = [],
                    requestId: UUID = UUID()) async throws -> AgentTaskDetail {
        try await client.request(method: "POST", path: "\(basePath)/\(taskId)/rounds",
                                 body: AgentTaskRoundRequest(requestId: requestId.uuidString.lowercased(), kind: kind,
                                                             directive: directive, itemIds: itemIds))
    }

    func cancel(_ taskId: String) async throws -> AgentTaskDetail {
        try await client.request(method: "POST", path: "\(basePath)/\(taskId)/cancel")
    }

    func delete(_ taskId: String) async throws {
        let _: [String: Bool] = try await client.request(method: "DELETE", path: "\(basePath)/\(taskId)")
    }

    /// What an action (buy, book...) would do for this finding. Nothing
    /// happens until `confirmAction`.
    func proposeAction(_ taskId: String, _ itemId: String, action: String,
                       params: [String: String]) async throws -> AgentTaskActionRun {
        try await client.request(method: "POST", path: "\(basePath)/\(taskId)/items/\(itemId)/actions/\(action)",
                                 body: AgentTaskActionRequest(params: params))
    }

    /// Carry out a proposal, once; a retry returns what came of it.
    func confirmAction(_ runId: String) async throws -> AgentTaskActionRun {
        try await client.request(method: "POST", path: "\(basePath)/actions/\(runId)/confirm")
    }

    func cancelAction(_ runId: String) async throws -> AgentTaskActionRun {
        try await client.request(method: "POST", path: "\(basePath)/actions/\(runId)/cancel")
    }

    /// Submit a form Espresso asked in chat: the task starts with no model
    /// run. A retry gets the same task.
    func answerForm(promptId: String, answer: IntakeFormAnswer) async throws -> AgentTask {
        try await client.request(method: "POST", path: "\(basePath)/prompts/\(promptId)/answer", body: answer)
    }
}
