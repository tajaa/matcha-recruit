import Foundation

// Espresso assistant: what it may do for a person, and what stands in the way.
// Server: routes/matcha_work/assistant.py (GET /assistant/abilities).

struct AssistantDisclosure: Decodable, Hashable {
    let version: String
    let title: String
    let body: [String]
}

struct AssistantContact: Codable, Hashable {
    var name: String
    var phone: String
    var email: String

    /// A booking needs a name and one way to reach the person.
    var isUsable: Bool {
        !name.trimmingCharacters(in: .whitespaces).isEmpty
            && (!phone.trimmingCharacters(in: .whitespaces).isEmpty
                || !email.trimmingCharacters(in: .whitespaces).isEmpty)
    }
}

struct AssistantAbility: Decodable, Identifiable, Hashable {
    let key: String
    let commitMode: String?
    let label: String
    /// Reading the web and comparing things to buy need nothing switched on.
    let alwaysOn: Bool
    let enabled: Bool
    let available: Bool
    /// Why it can't be used yet, in the person's terms.
    let reason: String?
    let needsConnection: Bool
    /// Whether it can act outward (send, invite, book), not just look.
    let acts: Bool
    let disclosure: AssistantDisclosure?
    /// They agreed to an older disclosure than the current one.
    let consentOutdated: Bool
    let contact: AssistantContact?

    var id: String { key }

    enum CodingKeys: String, CodingKey {
        case key, label, enabled, available, reason, acts, disclosure, settings
        case commitMode = "commit_mode"
        case alwaysOn = "always_on"
        case needsConnection = "needs_connection"
        case consentOutdated = "consent_outdated"
    }

    private struct Settings: Decodable {
        struct Contact: Decodable {
            let name: String?
            let phone: String?
            let email: String?
        }
        let contact: Contact?
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        key = try c.decode(String.self, forKey: .key)
        commitMode = try c.decodeIfPresent(String.self, forKey: .commitMode)
        label = (try? c.decode(String.self, forKey: .label)) ?? key
        alwaysOn = (try? c.decode(Bool.self, forKey: .alwaysOn)) ?? false
        enabled = (try? c.decode(Bool.self, forKey: .enabled)) ?? false
        available = (try? c.decode(Bool.self, forKey: .available)) ?? false
        reason = try? c.decodeIfPresent(String.self, forKey: .reason)
        needsConnection = (try? c.decode(Bool.self, forKey: .needsConnection)) ?? false
        acts = (try? c.decode(Bool.self, forKey: .acts)) ?? false
        disclosure = try? c.decodeIfPresent(AssistantDisclosure.self, forKey: .disclosure)
        consentOutdated = (try? c.decode(Bool.self, forKey: .consentOutdated)) ?? false
        let saved = (try? c.decodeIfPresent(Settings.self, forKey: .settings))?.contact
        contact = saved.map {
            AssistantContact(name: $0.name ?? "", phone: $0.phone ?? "", email: $0.email ?? "")
        }
    }
}

struct AssistantAbilities: Decodable {
    struct Google: Decodable {
        let connected: Bool
    }

    let abilities: [AssistantAbility]
    let google: Google
    /// "dry_run" until the server is switched to "live": nothing leaves the system.
    let commitMode: String

    enum CodingKeys: String, CodingKey {
        case abilities, google
        case commitMode = "commit_mode"
    }

    var isDryRun: Bool { commitMode != "live" }
}


struct AssistantConversation: Decodable, Identifiable {
    let id: String
    let title: String
    let updatedAt: String?
    enum CodingKeys: String, CodingKey {
        case id, title
        case updatedAt = "updated_at"
    }
}

struct AssistantConversationList: Decodable {
    let conversations: [AssistantConversation]
    let hasMore: Bool
    enum CodingKeys: String, CodingKey {
        case conversations
        case hasMore = "has_more"
    }
}

/// IDs only: mail bodies and sender-controlled text stay out of the user's prompt.
struct AssistantEmailContext: Identifiable {
    let id = UUID()
    let emails: [EmailMessage]
    var prompt: String {
        let refs = emails.map { message in
            "- Message \(message.id)" + (message.threadId.map { " (thread \($0))" } ?? "")
        }.joined(separator: "\n")
        return "Help me work with these Gmail messages. Read the relevant messages before drafting replies or organizing them.\n\n\(refs)\n\nMy instructions: "
    }
}

/// Serializes conversation operations and drains the latest email handoff.
/// A failed request stays pending for explicit retry with the same UUID.
@Observable
@MainActor
final class AssistantOperationQueue {
    private(set) var loading = false
    @ObservationIgnored private var queuedHandoff: (() async -> Void)?

    func run(_ operation: () async -> Void) async {
        guard !loading else { return }
        loading = true
        await operation()
        loading = false
        let next = queuedHandoff
        queuedHandoff = nil
        await next?()
    }

    func takeEmails(
        pending: @escaping () -> AssistantEmailContext?,
        create: @escaping (AssistantEmailContext) async throws -> String,
        select: @escaping (String, String) -> Void,
        consume: @escaping (UUID) -> Void,
        report: @escaping (Error) -> Void
    ) async {
        guard let request = pending() else { return }
        let again = { await self.takeEmails(pending: pending, create: create, select: select,
                                            consume: consume, report: report) }
        guard !loading else {
            queuedHandoff = again
            return
        }
        await run {
            do {
                let id = try await create(request)
                // The user may have chosen different mail while create/list
                // awaited. Never select that older result over their new one.
                guard pending()?.id == request.id else {
                    if pending() != nil { queuedHandoff = again }
                    return
                }
                select(id, request.prompt)
                consume(request.id)
            } catch { report(error) }
        }
    }
}
