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
