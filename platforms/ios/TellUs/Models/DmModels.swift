import Foundation

// Mirrors client/tellus/src/api/types.ts and server/app/tellus/models/tellus.py.

enum DmSenderRole: String, Codable, FallbackDecodable { case brand, consumer, unknown }
enum DmKind: String, Codable, FallbackDecodable { case feedback, general, unknown }
enum DmTopic: String, Codable, CaseIterable, FallbackDecodable {
    case hours, availability, inventory, order, service, accessibility, other, unknown
}
enum DmStatus: String, Codable, FallbackDecodable {
    case waiting_brand, waiting_consumer, closed, unknown
}

struct DmThread: Codable, Identifiable, Hashable {
    let id: String
    let report_id: String?
    let counterparty_name: String
    let report_title: String?
    let report_number: String?
    let review_state: ReviewState?
    let publish_at: String?
    let blocked: Bool
    let unread_count: Int
    let last_message_at: String
    let created_at: String
    let kind: DmKind
    let topic: DmTopic?
    let status: DmStatus
    let store_id: String?
    let store_name: String?
    let store_city: String?
    let assigned_member_id: String?
    let assigned_member_name: String?
    let viewer_role: DmSenderRole?
    let first_brand_response_at: String?
    let closed_at: String?

    init(
        id: String,
        report_id: String? = nil,
        counterparty_name: String,
        report_title: String? = nil,
        report_number: String? = nil,
        review_state: ReviewState? = nil,
        publish_at: String? = nil,
        blocked: Bool,
        unread_count: Int,
        last_message_at: String,
        created_at: String,
        kind: DmKind = .feedback,
        topic: DmTopic? = nil,
        status: DmStatus = .waiting_consumer,
        store_id: String? = nil,
        store_name: String? = nil,
        store_city: String? = nil,
        assigned_member_id: String? = nil,
        assigned_member_name: String? = nil,
        viewer_role: DmSenderRole? = nil,
        first_brand_response_at: String? = nil,
        closed_at: String? = nil
    ) {
        self.id = id
        self.report_id = report_id
        self.counterparty_name = counterparty_name
        self.report_title = report_title
        self.report_number = report_number
        self.review_state = review_state
        self.publish_at = publish_at
        self.blocked = blocked
        self.unread_count = unread_count
        self.last_message_at = last_message_at
        self.created_at = created_at
        self.kind = kind
        self.topic = topic
        self.status = status
        self.store_id = store_id
        self.store_name = store_name
        self.store_city = store_city
        self.assigned_member_id = assigned_member_id
        self.assigned_member_name = assigned_member_name
        self.viewer_role = viewer_role
        self.first_brand_response_at = first_brand_response_at
        self.closed_at = closed_at
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(String.self, forKey: .id)
        report_id = try c.decodeIfPresent(String.self, forKey: .report_id)
        counterparty_name = try c.decode(String.self, forKey: .counterparty_name)
        report_title = try c.decodeIfPresent(String.self, forKey: .report_title)
        report_number = try c.decodeIfPresent(String.self, forKey: .report_number)
        review_state = try c.decodeIfPresent(ReviewState.self, forKey: .review_state)
        publish_at = try c.decodeIfPresent(String.self, forKey: .publish_at)
        blocked = try c.decode(Bool.self, forKey: .blocked)
        unread_count = try c.decode(Int.self, forKey: .unread_count)
        last_message_at = try c.decode(String.self, forKey: .last_message_at)
        created_at = try c.decode(String.self, forKey: .created_at)
        kind = try c.decodeIfPresent(DmKind.self, forKey: .kind) ?? .feedback
        topic = try c.decodeIfPresent(DmTopic.self, forKey: .topic)
        status = try c.decodeIfPresent(DmStatus.self, forKey: .status) ?? .waiting_consumer
        store_id = try c.decodeIfPresent(String.self, forKey: .store_id)
        store_name = try c.decodeIfPresent(String.self, forKey: .store_name)
        store_city = try c.decodeIfPresent(String.self, forKey: .store_city)
        assigned_member_id = try c.decodeIfPresent(String.self, forKey: .assigned_member_id)
        assigned_member_name = try c.decodeIfPresent(String.self, forKey: .assigned_member_name)
        viewer_role = try c.decodeIfPresent(DmSenderRole.self, forKey: .viewer_role)
        first_brand_response_at = try c.decodeIfPresent(String.self, forKey: .first_brand_response_at)
        closed_at = try c.decodeIfPresent(String.self, forKey: .closed_at)
    }

    func with(blocked: Bool) -> DmThread {
        DmThread(id: id, report_id: report_id, counterparty_name: counterparty_name,
                 report_title: report_title, report_number: report_number,
                 review_state: review_state, publish_at: publish_at, blocked: blocked,
                 unread_count: unread_count, last_message_at: last_message_at,
                 created_at: created_at, kind: kind, topic: topic, status: status,
                 store_id: store_id, store_name: store_name, store_city: store_city,
                 assigned_member_id: assigned_member_id,
                 assigned_member_name: assigned_member_name, viewer_role: viewer_role,
                 first_brand_response_at: first_brand_response_at, closed_at: closed_at)
    }
}

struct DmMessage: Codable, Identifiable {
    let id: String
    let thread_id: String
    let sender_role: DmSenderRole
    let body: String
    let created_at: String
    let is_mine: Bool
}

struct DmSend: Encodable {
    let body: String
    let client_message_id: String?

    init(body: String, clientMessageId: String? = nil) {
        self.body = body
        self.client_message_id = clientMessageId
    }
}

struct CommsStartRequest: Encodable {
    let store_id: String?
    let topic: DmTopic
    let body: String
    let client_message_id: String

    init(storeID: String?, topic: DmTopic, body: String, clientMessageId: String) {
        self.store_id = storeID
        self.topic = topic
        self.body = body
        self.client_message_id = clientMessageId
    }
}

struct CommsStartResponse: Decodable {
    let thread: DmThread
    let message: DmMessage
}

struct InboxBrand: Codable, Identifiable, Hashable {
    let brand_id: String
    let name: String
    let slug: String
    let plan_status: BrandPlanStatus?
    let role: String
    let can_manage_inbox: Bool
    var id: String { brand_id }
}

struct MessagingStore: Codable, Identifiable, Hashable {
    let id: String
    let name: String
    let address: String?
    let city: String?
    let state: String?
}

struct PublicBrandPage: Decodable {
    let brand_name: String
    let slug: String
    let claimed: Bool
    let messaging_enabled: Bool
    let stores: [MessagingStore]
}

struct InboxToggleRequest: Encodable { let enabled: Bool }
struct ThreadAssignmentRequest: Encodable { let member_id: String? }
