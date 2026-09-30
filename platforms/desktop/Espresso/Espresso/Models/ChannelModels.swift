import Foundation

struct ChannelAttachment: Codable, Hashable {
    let url: String
    let filename: String
    let contentType: String
    let size: Int

    enum CodingKeys: String, CodingKey {
        case url, filename, size
        case contentType = "content_type"
    }
}

struct ChannelMember: Codable, Identifiable, Hashable {
    let userId: String
    let name: String
    let email: String
    let role: String
    let channelRole: String
    let avatarUrl: String?
    let joinedAt: String

    var id: String { userId }

    enum CodingKeys: String, CodingKey {
        case name, email, role
        case userId = "user_id"
        case channelRole = "channel_role"
        case avatarUrl = "avatar_url"
        case joinedAt = "joined_at"
    }
}

struct ChannelReaction: Codable, Hashable {
    let emoji: String
    let userIds: [String]
    let count: Int

    enum CodingKeys: String, CodingKey {
        case emoji, count
        case userIds = "user_ids"
    }
}

struct ReplyPreview: Codable, Hashable {
    let id: String
    let senderName: String
    let content: String
    let attachments: [ChannelAttachment]

    enum CodingKeys: String, CodingKey {
        case id, content, attachments
        case senderName = "sender_name"
    }

    init(id: String, senderName: String, content: String, attachments: [ChannelAttachment] = []) {
        self.id = id; self.senderName = senderName; self.content = content; self.attachments = attachments
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.id = try c.decode(String.self, forKey: .id)
        self.senderName = try c.decode(String.self, forKey: .senderName)
        self.content = try c.decode(String.self, forKey: .content)
        self.attachments = (try? c.decode([ChannelAttachment].self, forKey: .attachments)) ?? []
    }
}

/// Optional domain pointer carried by Huume/system messages. The desktop
/// decoder keeps this additive so older messages without metadata continue to
/// decode unchanged; action execution remains server-authorized.
struct ChannelActionReference: Codable, Hashable {
    let kind: String
    let id: String
    let status: String?
}

struct ChannelMessageMetadata: Codable, Hashable {
    let action: ChannelActionReference?
    /// Espresso agent-card payloads (server: agent_card/chat_flow.py).
    /// `kind` is agent_card_result / agent_card_prompt / agent_card_receipt.
    let kind: String?
    let promptKind: String?
    let promptId: String?
    let taskId: String?
    /// Buy / card questions answer only to this user, so only they get buttons.
    let ownerUserId: String?
    /// ISO time the question stops taking answers.
    let expiresAt: String?
    /// Live question state: open / answered / superseded / expired. Stamped
    /// onto history, and kept live by the `agent_card_prompt_updated` socket
    /// event. Absent on a just-posted question (open).
    var promptStatus: String?
    var answer: String?
    /// How the answer reads on the card ("Showed the result").
    var answerText: String?
    let view: AgentChatPromptView?
    let result: AgentChatResult?
    let receipt: AgentChatReceipt?
    /// Espresso assistant payloads (server: agent_runtime/). `kind` is
    /// agent_progress / agent_result / agent_receipt.
    let runId: String?
    /// A run's state: stamped onto history, and kept live by the
    /// `agent_run_progress` socket event.
    var progress: AgentRunProgress?
    let resultV2: AgentChatResultV2?
    let actionReceipt: AgentActionReceipt?

    enum CodingKeys: String, CodingKey {
        case action, kind, answer, view, result, receipt, progress
        case runId = "run_id"
        case resultV2 = "result_v2"
        case actionReceipt = "action_receipt"
        case promptKind = "prompt_kind"
        case promptId = "prompt_id"
        case taskId = "task_id"
        case ownerUserId = "owner_user_id"
        case expiresAt = "expires_at"
        case promptStatus = "prompt_status"
        case answerText = "answer_text"
    }

    init(action: ChannelActionReference? = nil) {
        self.action = action
        kind = nil; promptKind = nil; promptId = nil; taskId = nil; ownerUserId = nil; expiresAt = nil
        promptStatus = nil; answer = nil; answerText = nil
        view = nil; result = nil; receipt = nil
        runId = nil; progress = nil; resultV2 = nil; actionReceipt = nil
    }

    // Every field is optional and decoded on its own, so one odd field never
    // costs the whole metadata (and with it the Huume action card).
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        action = try? c.decodeIfPresent(ChannelActionReference.self, forKey: .action)
        kind = try? c.decodeIfPresent(String.self, forKey: .kind)
        promptKind = try? c.decodeIfPresent(String.self, forKey: .promptKind)
        promptId = try? c.decodeIfPresent(String.self, forKey: .promptId)
        taskId = try? c.decodeIfPresent(String.self, forKey: .taskId)
        ownerUserId = try? c.decodeIfPresent(String.self, forKey: .ownerUserId)
        expiresAt = try? c.decodeIfPresent(String.self, forKey: .expiresAt)
        promptStatus = try? c.decodeIfPresent(String.self, forKey: .promptStatus)
        answer = try? c.decodeIfPresent(String.self, forKey: .answer)
        answerText = try? c.decodeIfPresent(String.self, forKey: .answerText)
        view = try? c.decodeIfPresent(AgentChatPromptView.self, forKey: .view)
        result = try? c.decodeIfPresent(AgentChatResult.self, forKey: .result)
        receipt = try? c.decodeIfPresent(AgentChatReceipt.self, forKey: .receipt)
        runId = try? c.decodeIfPresent(String.self, forKey: .runId)
        progress = try? c.decodeIfPresent(AgentRunProgress.self, forKey: .progress)
        resultV2 = try? c.decodeIfPresent(AgentChatResultV2.self, forKey: .resultV2)
        actionReceipt = try? c.decodeIfPresent(AgentActionReceipt.self, forKey: .actionReceipt)
    }

    var isAgentCard: Bool {
        switch kind {
        case "agent_card_result": return result != nil
        case "agent_card_prompt": return view != nil
        case "agent_card_receipt": return receipt != nil
        case "agent_progress": return runId != nil
        case "agent_result": return resultV2 != nil
        case "agent_receipt": return actionReceipt != nil
        default: return false
        }
    }

    /// A question the assistant asked (answered by whoever it asked), not an
    /// agent card's buy / card question (answered by the buyer).
    var isAssistantPrompt: Bool {
        promptKind == "ask_user" || promptKind == "confirm_action"
    }
}

// MARK: - Espresso assistant (server: agent_runtime/)

struct AgentProgressStep: Codable, Hashable {
    let seq: Int
    let kind: String
    let label: String
    let status: String
}

struct AgentRunProgress: Codable, Hashable {
    let runId: String
    /// queued / running / done / failed
    let status: String
    let note: String?
    let steps: [AgentProgressStep]

    enum CodingKeys: String, CodingKey {
        case status, note, steps
        case runId = "run_id"
    }

    init(runId: String, status: String, note: String?, steps: [AgentProgressStep]) {
        self.runId = runId; self.status = status; self.note = note; self.steps = steps
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        runId = try c.decode(String.self, forKey: .runId)
        status = (try? c.decode(String.self, forKey: .status)) ?? "running"
        note = try? c.decodeIfPresent(String.self, forKey: .note)
        steps = (try? c.decodeIfPresent([AgentProgressStep].self, forKey: .steps)) ?? []
    }

    var isWorking: Bool { status == "queued" || status == "running" }
}

struct AgentActionLine: Codable, Hashable {
    let label: String
    let value: String
    let mono: Bool?
}

struct AgentActionLink: Codable, Hashable {
    let label: String?
    let url: String
}

/// Exactly what a yes will carry out (on a `confirm_action` question).
struct AgentChatAction: Codable, Hashable {
    let title: String?
    let lines: [AgentActionLine]

    enum CodingKeys: String, CodingKey { case title, lines }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        title = try? c.decodeIfPresent(String.self, forKey: .title)
        lines = (try? c.decodeIfPresent([AgentActionLine].self, forKey: .lines)) ?? []
    }
}

/// Something Espresso did for the person: sent, invited, booked, archived.
struct AgentActionReceipt: Codable, Hashable {
    let action: String?
    let title: String
    /// done / dry_run / unknown / failed / handoff
    let status: String
    let lines: [AgentActionLine]
    let link: AgentActionLink?
    let note: String?

    enum CodingKeys: String, CodingKey { case action, title, status, lines, link, note }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        action = try? c.decodeIfPresent(String.self, forKey: .action)
        title = (try? c.decode(String.self, forKey: .title)) ?? ""
        status = (try? c.decode(String.self, forKey: .status)) ?? "done"
        lines = (try? c.decodeIfPresent([AgentActionLine].self, forKey: .lines)) ?? []
        link = try? c.decodeIfPresent(AgentActionLink.self, forKey: .link)
        note = try? c.decodeIfPresent(String.self, forKey: .note)
    }
}

struct AgentSection: Codable, Hashable {
    let heading: String
    let bodyMd: String

    enum CodingKeys: String, CodingKey {
        case heading
        case bodyMd = "body_md"
    }
}

struct AgentSource: Codable, Hashable {
    let title: String?
    let url: String
}

struct AgentEmailItem: Codable, Hashable {
    let messageId: String
    let from: String
    let subject: String
    let date: String?
    let snippet: String?

    enum CodingKeys: String, CodingKey {
        case from, subject, date, snippet
        case messageId = "message_id"
    }
}

struct AgentEventItem: Codable, Hashable {
    let eventId: String
    let title: String
    let start: String
    let end: String?
    let location: String?
    let attendeeCount: Int?

    enum CodingKeys: String, CodingKey {
        case title, start, end, location
        case eventId = "event_id"
        case attendeeCount = "attendee_count"
    }
}

struct AgentReservation: Codable, Hashable {
    let venue: String
    let when: String
    let partySize: Int
    /// booked / unverified / unavailable / handoff / blocked / failed
    let status: String
    let confirmation: String?
    let handoffUrl: String?

    enum CodingKeys: String, CodingKey {
        case venue, when, status, confirmation
        case partySize = "party_size"
        case handoffUrl = "handoff_url"
    }
}

/// One typed part of an answer. A block type this build doesn't know decodes
/// to `.unknown` and is skipped: the server can add one before the app does.
enum AgentResultBlock: Codable, Hashable {
    case picks(top: AgentChatPick?, alternatives: [AgentChatPick])
    case flights(AgentChatFlights)
    case sections([AgentSection])
    case sources([AgentSource])
    case emails([AgentEmailItem])
    case events([AgentEventItem])
    case reservation(AgentReservation)
    case unknown(String)

    private enum CodingKeys: String, CodingKey {
        case type, sections, sources, items, alternatives, flights
        case topPick = "top_pick"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        let type = (try? c.decode(String.self, forKey: .type)) ?? ""
        switch type {
        case "picks":
            self = .picks(
                top: try? c.decodeIfPresent(AgentChatPick.self, forKey: .topPick),
                alternatives: (try? c.decodeIfPresent([AgentChatPick].self, forKey: .alternatives)) ?? []
            )
        case "flights":
            if let flights = try? c.decode(AgentChatFlights.self, forKey: .flights) {
                self = .flights(flights)
            } else {
                self = .unknown(type)
            }
        case "sections":
            self = .sections((try? c.decodeIfPresent([AgentSection].self, forKey: .sections)) ?? [])
        case "sources":
            self = .sources((try? c.decodeIfPresent([AgentSource].self, forKey: .sources)) ?? [])
        case "emails":
            self = .emails((try? c.decodeIfPresent([AgentEmailItem].self, forKey: .items)) ?? [])
        case "events":
            self = .events((try? c.decodeIfPresent([AgentEventItem].self, forKey: .items)) ?? [])
        case "reservation":
            if let booking = try? AgentReservation(from: decoder) {
                self = .reservation(booking)
            } else {
                self = .unknown(type)
            }
        default:
            self = .unknown(type)
        }
    }

    // Message metadata is Codable as a whole, so a block writes back what it read.
    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        switch self {
        case .picks(let top, let alternatives):
            try c.encode("picks", forKey: .type)
            try c.encodeIfPresent(top, forKey: .topPick)
            try c.encode(alternatives, forKey: .alternatives)
        case .flights(let flights):
            try c.encode("flights", forKey: .type)
            try c.encode(flights, forKey: .flights)
        case .sections(let sections):
            try c.encode("sections", forKey: .type)
            try c.encode(sections, forKey: .sections)
        case .sources(let sources):
            try c.encode("sources", forKey: .type)
            try c.encode(sources, forKey: .sources)
        case .emails(let items):
            try c.encode("emails", forKey: .type)
            try c.encode(items, forKey: .items)
        case .events(let items):
            try c.encode("events", forKey: .type)
            try c.encode(items, forKey: .items)
        case .reservation(let booking):
            try booking.encode(to: encoder)
            try c.encode("reservation", forKey: .type)
        case .unknown(let type):
            try c.encode(type, forKey: .type)
        }
    }
}

struct AgentChatResultV2: Codable, Hashable {
    let headline: String
    let summary: String
    let blocks: [AgentResultBlock]
    let caveats: [String]
    let confidence: String?

    enum CodingKeys: String, CodingKey { case headline, summary, blocks, caveats, confidence }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        headline = (try? c.decode(String.self, forKey: .headline)) ?? ""
        summary = (try? c.decode(String.self, forKey: .summary)) ?? ""
        blocks = (try? c.decodeIfPresent([AgentResultBlock].self, forKey: .blocks)) ?? []
        caveats = (try? c.decodeIfPresent([String].self, forKey: .caveats)) ?? []
        confidence = try? c.decodeIfPresent(String.self, forKey: .confidence)
    }
}

struct AgentChatButton: Codable, Hashable {
    let label: String
    /// Sent verbatim as a threaded reply to the question.
    let reply: String
    let style: String?
    let detail: String?
}

struct AgentChatOffer: Codable, Hashable {
    let itemName: String
    let brand: String?
    let retailer: String?
    let priceText: String?
    let imageUrl: String?

    enum CodingKeys: String, CodingKey {
        case brand, retailer
        case itemName = "item_name"
        case priceText = "price_text"
        case imageUrl = "image_url"
    }
}

struct AgentChatPromptView: Codable, Hashable {
    let question: String?
    let offer: AgentChatOffer?
    /// `confirm_action`: exactly what a yes will carry out.
    let action: AgentChatAction?
    let buttons: [AgentChatButton]

    enum CodingKeys: String, CodingKey { case question, offer, action, buttons }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        question = try? c.decodeIfPresent(String.self, forKey: .question)
        offer = try? c.decodeIfPresent(AgentChatOffer.self, forKey: .offer)
        action = try? c.decodeIfPresent(AgentChatAction.self, forKey: .action)
        // A question with no suggested answers is answered by typing.
        buttons = (try? c.decodeIfPresent([AgentChatButton].self, forKey: .buttons)) ?? []
    }
}

struct AgentChatRating: Codable, Hashable {
    let value: Double
    let scale: Double?
    let count: Int?
}

struct AgentChatPick: Codable, Hashable {
    let name: String
    let brand: String?
    let imageUrl: String?
    let priceText: String?
    let buyUrl: String?
    let retailer: String?
    let rating: AgentChatRating?
    let why: [String]?

    enum CodingKeys: String, CodingKey {
        case name, brand, retailer, rating, why
        case imageUrl = "image_url"
        case priceText = "price_text"
        case buyUrl = "buy_url"
    }
}

struct AgentChatFlightSlice: Codable, Hashable {
    let origin: String
    let destination: String
    let departingAt: String
    let arrivingAt: String
    let stops: Int
    let durationMinutes: Int?

    enum CodingKeys: String, CodingKey {
        case origin, destination, stops
        case departingAt = "departing_at"
        case arrivingAt = "arriving_at"
        case durationMinutes = "duration_minutes"
    }
}

struct AgentChatFlightOption: Codable, Hashable {
    let label: String?
    let priceText: String?
    let totalWithBagsText: String?
    let carriers: [String]
    let ticketing: String
    let slices: [AgentChatFlightSlice]
    let warning: String?

    enum CodingKeys: String, CodingKey {
        case label, carriers, ticketing, slices, warning
        case priceText = "price_text"
        case totalWithBagsText = "total_with_bags_text"
    }
}

/// A flight search's top chosen offers (server: chat_flow.flights_view).
struct AgentChatFlights: Codable, Hashable {
    let testData: Bool?
    let options: [AgentChatFlightOption]

    enum CodingKeys: String, CodingKey {
        case options
        case testData = "test_data"
    }
}

struct AgentChatResult: Codable, Hashable {
    let headline: String
    let summary: String
    let topPick: AgentChatPick?
    let alternatives: [AgentChatPick]
    let sections: [String]?
    let flights: AgentChatFlights?
    let sourceCount: Int?

    enum CodingKeys: String, CodingKey {
        case headline, summary, alternatives, sections, flights
        case topPick = "top_pick"
        case sourceCount = "source_count"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        headline = try c.decode(String.self, forKey: .headline)
        summary = try c.decode(String.self, forKey: .summary)
        topPick = try c.decodeIfPresent(AgentChatPick.self, forKey: .topPick)
        alternatives = try c.decode([AgentChatPick].self, forKey: .alternatives)
        sections = try c.decodeIfPresent([String].self, forKey: .sections)
        // Lenient: an odd flights block never costs the whole result card.
        flights = try? c.decodeIfPresent(AgentChatFlights.self, forKey: .flights)
        sourceCount = try c.decodeIfPresent(Int.self, forKey: .sourceCount)
    }
}

struct AgentChatReceipt: Codable, Hashable {
    /// paid_test / approved / no_price / failed
    let status: String
    let itemName: String
    let brand: String?
    let imageUrl: String?
    let retailer: String?
    let totalText: String?
    let currency: String?
    let cardText: String?
    let paymentIntentId: String?
    let orderRef: String?
    let date: String?
    let productUrl: String?
    let error: String?

    enum CodingKeys: String, CodingKey {
        case status, brand, retailer, currency, date, error
        case itemName = "item_name"
        case imageUrl = "image_url"
        case totalText = "total_text"
        case cardText = "card_text"
        case paymentIntentId = "payment_intent_id"
        case orderRef = "order_ref"
        case productUrl = "product_url"
    }
}

struct ChannelMessage: Codable, Identifiable, Hashable {
    let id: String
    let channelId: String
    let senderId: String
    let senderName: String
    let senderAvatarUrl: String?
    var content: String
    let attachments: [ChannelAttachment]
    let replyToId: String?
    let replyPreview: ReplyPreview?
    var reactions: [ChannelReaction]
    let createdAt: String
    var editedAt: String?
    var deletedAt: String?
    var deletedBy: String?
    /// User IDs the server resolved from @mentions in `content`. Only populated
    /// on broadcasts from the live channels WS — older REST-fetched messages
    /// won't carry this; renderers may still parse @handle patterns from
    /// `content` for display.
    let mentionedUserIds: [String]?
    /// Client-generated correlation ID used to reconcile optimistic-pending
    /// entries with their server echo. Round-trips through the WS payload.
    let clientMessageId: String?
    /// `var` so a live agent-card question update can restamp its state.
    var metadata: ChannelMessageMetadata?
    /// Local-only flag: true while a sent message is awaiting server echo.
    /// Not encoded; the custom decoder always sets this to false. Mutable
    /// so the failure-timeout in ChannelChatViewModel can flip it off when
    /// promoting a stuck pending entry to `failed`.
    var pending: Bool
    /// Local-only flag: set to true when an optimistic-pending message has
    /// not received its server echo within the failure timeout. Renderer
    /// shows a red error affordance; delete is disabled in this state too.
    /// Not encoded.
    var failed: Bool

    enum CodingKeys: String, CodingKey {
        case id, content, attachments, reactions
        case channelId = "channel_id"
        case senderId = "sender_id"
        case senderName = "sender_name"
        case senderAvatarUrl = "sender_avatar_url"
        case replyToId = "reply_to_id"
        case replyPreview = "reply_preview"
        case createdAt = "created_at"
        case editedAt = "edited_at"
        case deletedAt = "deleted_at"
        case deletedBy = "deleted_by"
        case mentionedUserIds = "mentioned_user_ids"
        case clientMessageId = "client_message_id"
        case metadata
    }

    init(id: String, channelId: String, senderId: String, senderName: String,
         senderAvatarUrl: String?, content: String, attachments: [ChannelAttachment],
         replyToId: String? = nil, replyPreview: ReplyPreview? = nil,
         reactions: [ChannelReaction] = [],
         createdAt: String, editedAt: String?,
         mentionedUserIds: [String]? = nil,
         clientMessageId: String? = nil,
         metadata: ChannelMessageMetadata? = nil,
         pending: Bool = false,
         failed: Bool = false) {
        self.id = id
        self.channelId = channelId
        self.senderId = senderId
        self.senderName = senderName
        self.senderAvatarUrl = senderAvatarUrl
        self.content = content
        self.attachments = attachments
        self.replyToId = replyToId
        self.replyPreview = replyPreview
        self.reactions = reactions
        self.createdAt = createdAt
        self.editedAt = editedAt
        self.mentionedUserIds = mentionedUserIds
        self.clientMessageId = clientMessageId
        self.metadata = metadata
        self.pending = pending
        self.failed = failed
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.id = try c.decode(String.self, forKey: .id)
        self.channelId = try c.decode(String.self, forKey: .channelId)
        self.senderId = try c.decode(String.self, forKey: .senderId)
        self.senderName = try c.decode(String.self, forKey: .senderName)
        self.senderAvatarUrl = try c.decodeIfPresent(String.self, forKey: .senderAvatarUrl)
        self.content = try c.decode(String.self, forKey: .content)
        self.attachments = (try? c.decode([ChannelAttachment].self, forKey: .attachments)) ?? []
        self.replyToId = try c.decodeIfPresent(String.self, forKey: .replyToId)
        self.replyPreview = try c.decodeIfPresent(ReplyPreview.self, forKey: .replyPreview)
        self.reactions = (try? c.decode([ChannelReaction].self, forKey: .reactions)) ?? []
        self.createdAt = try c.decode(String.self, forKey: .createdAt)
        self.editedAt = try c.decodeIfPresent(String.self, forKey: .editedAt)
        self.mentionedUserIds = try? c.decodeIfPresent([String].self, forKey: .mentionedUserIds)
        self.clientMessageId = try? c.decodeIfPresent(String.self, forKey: .clientMessageId)
        self.metadata = try? c.decodeIfPresent(ChannelMessageMetadata.self, forKey: .metadata)
        self.pending = false
        self.failed = false
    }

    /// SwiftUI ForEach key that stays stable across the optimistic→confirmed
    /// swap. Sender's pending row and its server echo share the same
    /// `clientMessageId`, so the row keeps its identity (no flicker / scroll
    /// jump) when the pending struct is replaced by the server version.
    /// Falls back to `id` for non-optimistic messages (REST-fetched history,
    /// other senders).
    var stableKey: String {
        if let cmid = clientMessageId, !cmid.isEmpty { return "cmid:\(cmid)" }
        return "id:\(id)"
    }
}

/// Channel categories — single source of truth on the client. Mirrors the
/// `CHANNEL_CATEGORIES` tuple in `server/app/core/routes/channels.py`. Update
/// both sides when adding.
enum ChannelCategory: String, CaseIterable, Identifiable {
    case general
    case engineering
    case design
    case sales
    case support
    case operations
    case marketing
    case hr
    case announcements

    var id: String { rawValue }

    var label: String {
        switch self {
        case .general: return "General"
        case .engineering: return "Engineering"
        case .design: return "Design"
        case .sales: return "Sales"
        case .support: return "Support"
        case .operations: return "Operations"
        case .marketing: return "Marketing"
        case .hr: return "HR"
        case .announcements: return "Announcements"
        }
    }
}

struct ChannelSummary: Codable, Identifiable, Hashable {
    let id: String
    let name: String
    let slug: String
    let description: String?
    let visibility: String
    let category: String?
    let isPaid: Bool
    let priceCents: Int?
    let currency: String?
    let memberCount: Int
    var unreadCount: Int
    let lastMessageAt: String?
    let lastMessagePreview: String?
    let isMember: Bool
    let myRole: String?
    /// Channel creator — founder chip on hub cards + mine/joined grouping.
    let createdById: String?
    let createdByName: String?
    let createdByAvatarUrl: String?
    /// Set when this channel is the auto-created discussion channel for a
    /// matcha-work collab project. Sidebar renders a "collab" badge.
    let projectId: String?
    let projectTitle: String?

    enum CodingKeys: String, CodingKey {
        case id, name, slug, description, visibility, category
        case isPaid = "is_paid"
        case priceCents = "price_cents"
        case currency
        case memberCount = "member_count"
        case unreadCount = "unread_count"
        case lastMessageAt = "last_message_at"
        case lastMessagePreview = "last_message_preview"
        case isMember = "is_member"
        case myRole = "my_role"
        case createdById = "created_by"
        case createdByName = "created_by_name"
        case createdByAvatarUrl = "created_by_avatar_url"
        case projectId = "project_id"
        case projectTitle = "project_title"
    }
}

struct ChannelDetail: Codable, Identifiable, Hashable {
    let id: String
    let name: String
    let slug: String
    let description: String?
    let visibility: String
    let category: String?
    let isPaid: Bool
    let priceCents: Int?
    let currency: String
    let isArchived: Bool
    let createdBy: String
    let createdAt: String
    let memberCount: Int
    let isMember: Bool
    let myRole: String?
    /// Set when this channel is a collab project's discussion chat — enables
    /// "Create ticket" from a message, pointed at that project's board.
    let projectId: String?
    let members: [ChannelMember]
    let messages: [ChannelMessage]

    enum CodingKeys: String, CodingKey {
        case id, name, slug, description, visibility, category, currency, members, messages
        case isPaid = "is_paid"
        case priceCents = "price_cents"
        case isArchived = "is_archived"
        case createdBy = "created_by"
        case createdAt = "created_at"
        case memberCount = "member_count"
        case isMember = "is_member"
        case myRole = "my_role"
        case projectId = "project_id"
    }
}

struct UserConnection: Codable, Identifiable, Hashable {
    let userId: String
    let name: String
    let email: String
    let avatarUrl: String?
    let createdAt: String

    var id: String { userId }

    enum CodingKeys: String, CodingKey {
        case name, email
        case userId = "user_id"
        case avatarUrl = "avatar_url"
        case createdAt = "created_at"
    }
}

struct ChannelOnlineUser: Codable, Identifiable, Hashable {
    let id: String
    let name: String
    let avatarUrl: String?

    enum CodingKeys: String, CodingKey {
        case id, name
        case avatarUrl = "avatar_url"
    }
}
