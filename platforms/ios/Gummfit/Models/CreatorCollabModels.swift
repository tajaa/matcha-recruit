import Foundation

struct CreatorSocial: Codable, Identifiable, Equatable { let id, platform, handle, url: String; let follower_count: Int?; let engagement_rate: Double?; let audit_status: String; let verified_follower_count: Int?; let audited_at: String?; let sort_order: Int }
struct CreatorPortfolioItem: Codable, Identifiable, Equatable { let id, title: String; let description, media_url, media_type, external_url, brand_name: String?; let metrics: [String: JSONValue]; let sort_order: Int; let created_at: String }
struct CreatorRate: Codable, Identifiable, Equatable { let id, deliverable_type, platform: String; let price_cents: Int; let negotiable: Bool; let notes: String?; let sort_order: Int }
struct CreatorProfileMe: Codable, Identifiable, Equatable { let id, handle, display_name: String; let avatar_url, cover_url, bio, location: String?; let niches, languages: [String]; let open_to_offers: Bool; let status, review_note, submitted_at, published_at: String?; let reach_verified: Bool; let reach_audited_at: String?; let socials: [CreatorSocial]; let portfolio: [CreatorPortfolioItem]; let rates: [CreatorRate] }
struct CreatorProfileCreate: Encodable { var handle, display_name: String }
struct CreatorProfileUpdate: Encodable { var display_name, avatar_url, cover_url, bio, location: String?; var niches, languages: [String]?; var open_to_offers: Bool? }
struct CreatorSocialInput: Encodable { var platform, handle, url: String; var follower_count: Int?; var engagement_rate: Double?; var sort_order: Int }
struct CreatorPortfolioInput: Encodable { var title: String; var description, media_url, media_type, external_url, brand_name: String?; var metrics: [String: JSONValue]; var sort_order: Int }
struct CreatorRateInput: Encodable { var deliverable_type, platform: String; var price_cents: Int; var negotiable: Bool; var notes: String?; var sort_order: Int }
struct EarningsRow: Codable, Identifiable, Equatable { var id: String { "\(offer_id)-\(label)" }; let offer_id, offer_title: String; let brand_name: String?; let label: String; let amount_cents: Int; let fee_cents: Int?; let status: String; let paid_at: String? }
struct OfferListItem: Codable, Identifiable, Equatable { let id, title, status: String; let payment_schedule: String?; let total_cents: Int?; let currency: String; let campaign_id, brand_name: String?; let creator_handle, creator_display_name: String; let creator_avatar_url: String?; let last_action_at, created_at: String }
struct OfferPage: Codable { let offers: [OfferListItem]; let total: Int }
struct OfferMessage: Codable, Identifiable, Equatable { let id, sender, body: String; let revision_id, created_at: String? }
struct Deliverable: Codable, Identifiable, Equatable { let id: String; let idx: Int; let type, platform: String; let spec, due_date: String?; let status, submission_url, submission_note, proof_media_url, submitted_at: String?; let revision_count: Int; let review_note, approved_at: String? }
struct CollabPayment: Codable, Identifiable, Equatable { let id: String; let idx: Int; let label: String; let amount_cents: Int; let currency, trigger, status: String; let deliverable_id: String?; let fee_cents: Int?; let due_at, paid_at: String? }
struct OfferDetail: Codable, Identifiable, Equatable { let id, title, status: String; let payment_schedule: String?; let total_cents: Int?; let currency: String; let campaign_id, brand_name: String?; let creator_handle, creator_display_name: String; let creator_avatar_url, last_action_at, created_at: String?; let side: String; let messages: [OfferMessage]; let deliverables: [Deliverable]; let payments: [CollabPayment]; let creator_payouts_ready: Bool; let auto_approve_days: Int }
struct OfferMessageCreate: Encodable { var body: String }
struct TermsDeliverable: Codable, Encodable { var type, platform: String; var quantity: Int; var spec, due_date: String? }
struct TermsUsageRights: Codable, Encodable { var scope: String; var duration_months: Int?; var whitelisting: Bool }
struct TermsExclusivity: Codable, Encodable { var category: String; var duration_months: Int }
struct CollabTerms: Codable, Encodable { var compensation_cents: Int; var payment_schedule: String; var deliverables: [TermsDeliverable]; var usage_rights: TermsUsageRights; var exclusivity: TermsExclusivity?; var revision_rounds: Int; var approval_required: Bool; var ftc_disclosure: Bool; var start_date, end_date, notes: String? }
struct OfferCounter: Encodable { var terms: CollabTerms; var message: String? }
struct CollabCampaign: Codable, Identifiable { let id, title: String; let description: String?; let budget_min_cents, budget_max_cents: Int?; let deliverable_notes: String?; let status: String; let offer_count: Int; let created_at: String }
struct CollabCampaignCreate: Encodable { var title: String; var description, deliverable_notes: String?; var budget_min_cents, budget_max_cents: Int?; var status: String? }
struct OfferCreate: Encodable { var creator_profile_id: String; var campaign_id: String?; var title: String; var terms: CollabTerms; var message: String? }
struct OfferDecline: Encodable { var reason: String? }
struct OfferCancel: Encodable { var reason: String }
struct DeliverableSubmit: Encodable { var submission_url: String; var submission_note, proof_media_url: String? }
struct DeliverableRevision: Encodable { var review_note: String }
