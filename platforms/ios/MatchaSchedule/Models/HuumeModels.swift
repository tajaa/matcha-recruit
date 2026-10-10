import Foundation

/// The schedule assistant's chat for one store and week
/// (`POST /employee-schedule/assistant/sessions`).
struct HuumeSession: Decodable {
    let session_id: String
    let thread_id: String
    let title: String?
    let messages: [HuumeMessage]
    let current_state: HuumeState
}

struct HuumeMessage: Decodable, Identifiable, Equatable {
    let id: String
    let role: String
    let content: String
    let created_at: String?

    var isUser: Bool { role == "user" }
}

/// The parts of the thread's `current_state` the phone acts on. Everything
/// else in it (reviews, plans, records) is the web's to render. Decoded
/// leniently: a state shape this build does not know only hides the card.
struct HuumeState: Decodable, Equatable {
    let action: HuumeAction?
    let choice: HuumeChoice?

    private enum CodingKeys: String, CodingKey {
        case action = "huume_action"
        case choice = "huume_choice"
    }

    init(action: HuumeAction? = nil, choice: HuumeChoice? = nil) {
        self.action = action
        self.choice = choice
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        action = try? container.decodeIfPresent(HuumeAction.self, forKey: .action)
        choice = try? container.decodeIfPresent(HuumeChoice.self, forKey: .choice)
    }
}

/// The one staged, confirm-first action. Confirm and Cancel are chat turns,
/// never a REST call: the server's two-turn rule decides.
struct HuumeAction: Decodable, Equatable {
    let type: String
    let status: String
    let pill_text: String?
    let summary: String?

    var awaitingConfirmation: Bool { status == "proposed" }

    /// What the card asks, in the server's words where it gave some.
    var question: String {
        if let first = pill_text?.split(separator: "\n", maxSplits: 1).first, !first.isEmpty {
            return String(first)
        }
        if let summary, !summary.isEmpty { return summary }
        switch type {
        case "schedule_week_draft": return "Add this week to the schedule as drafts?"
        case "schedule_change": return "Apply this schedule change?"
        default: return "Confirm this change?"
        }
    }

    /// The action went through, so the week behind the chat is stale.
    var changedSchedule: Bool { ["applied", "created", "updated", "saved"].contains(status) }
}

struct HuumeChoice: Decodable, Equatable {
    struct Option: Decodable, Equatable {
        let label: String
        let send: String?
    }

    let question: String
    let options: [Option]
}

/// One server-sent event from a turn
/// (`POST /matcha-work/threads/{id}/messages/stream`).
enum HuumeEvent: Equatable {
    case status(String)
    case step(String?)
    case complete(user: HuumeMessage?, assistant: HuumeMessage?, state: HuumeState?)
    /// Provisional: a turn can recover and still complete.
    case error(String)
    case done
}

enum HuumeSSE {
    private struct Frame: Decodable {
        struct Complete: Decodable {
            let user_message: HuumeMessage?
            let assistant_message: HuumeMessage?
            let current_state: HuumeState?
        }

        struct Step: Decodable { let label: String?; let tool: String? }

        let type: String
        let message: String?
        let data: Complete?
        let step: Step?

        private enum CodingKeys: String, CodingKey { case type, message, data }

        init(from decoder: Decoder) throws {
            let container = try decoder.container(keyedBy: CodingKeys.self)
            type = try container.decode(String.self, forKey: .type)
            message = try? container.decodeIfPresent(String.self, forKey: .message)
            data = type == "complete" ? try? container.decodeIfPresent(Complete.self, forKey: .data) : nil
            step = type == "step" ? try? container.decodeIfPresent(Step.self, forKey: .data) : nil
        }
    }

    /// One line of the stream as an event, or nil for anything to skip
    /// (blank lines, comments, keepalives, usage, unknown types).
    static func parse(line: String) -> HuumeEvent? {
        guard line.hasPrefix("data:") else { return nil }
        let payload = line.dropFirst(5).trimmingCharacters(in: .whitespaces)
        if payload == "[DONE]" { return .done }
        guard let frame = try? JSONDecoder().decode(Frame.self, from: Data(payload.utf8)) else { return nil }
        switch frame.type {
        case "status": return frame.message.map(HuumeEvent.status)
        case "step": return .step(frame.step?.label ?? frame.step?.tool)
        case "error": return .error(frame.message ?? "Huume ran into a problem.")
        case "complete":
            return .complete(
                user: frame.data?.user_message,
                assistant: frame.data?.assistant_message,
                state: frame.data?.current_state
            )
        default: return nil
        }
    }
}
