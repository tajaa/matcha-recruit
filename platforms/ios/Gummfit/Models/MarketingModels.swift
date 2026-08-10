import Foundation

struct CappeSubscriber: Codable, Identifiable, Equatable { let id, site_id, email: String; let name: String?; let status, source, created_at: String; let unsubscribed_at: String? }
struct CappeSubscriberCreate: Encodable { var email: String; var name: String?; var source = "manual" }
struct CappeCampaign: Codable, Identifiable, Equatable { let id, site_id, subject: String; let body_html, from_name: String?; let status, scheduled_at, sent_at: String?; let recipient_count: Int; let created_at, updated_at: String }
struct CappeCampaignCreate: Encodable { var subject: String; var body_html, from_name, scheduled_at: String? }
struct CappeCampaignUpdate: Encodable { var subject, body_html, from_name, scheduled_at, status: String? }
struct CappeFormField: Codable, Identifiable, Equatable { var id: String { key }; var key, label, type: String; var required: Bool; var options: [String]? }
struct CappeForm: Codable, Identifiable, Equatable { let id, site_id, name, slug: String; var fields: [CappeFormField]; var status: String; let created_at, updated_at: String }
struct CappeFormCreate: Encodable { var name: String; var slug: String?; var fields: [CappeFormField]; var status = "active" }
struct CappeFormUpdate: Encodable { var name: String?; var fields: [CappeFormField]?; var status: String? }
struct CappeFormSubmission: Codable, Identifiable, Equatable { let id, form_id: String; let data: [String: JSONValue]; let submitter_email: String?; var is_read: Bool; let created_at: String }
struct CappePost: Codable, Identifiable, Equatable { let id, site_id, title, slug: String; let excerpt, body, cover_image_url: String?; var status: String; let published_at, created_at, updated_at: String? }
struct CappePostCreate: Encodable { var title: String; var slug, excerpt, body, cover_image_url: String?; var status = "draft" }
struct CappePostUpdate: Encodable { var title, slug, excerpt, body, cover_image_url, status: String? }
