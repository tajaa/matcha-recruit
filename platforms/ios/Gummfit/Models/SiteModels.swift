import Foundation

/// Mirrors server/app/cappe/models/sites.py + client/src/cappe/types.ts:51-80.
/// Deliberately a subset — only fields Phase 1/2 (list/create/switch/readiness/
/// publish) touch; theme_config/meta_config/tax/shipping land with Catalog
/// (Phase 3) if a screen needs them. Extra wire fields are ignored by
/// JSONDecoder, so this narrows safely.
struct CappeSite: Codable, Identifiable, Equatable {
    let id: String
    let account_id: String
    let name: String
    let slug: String
    let subdomain: String?
    let custom_domain: String?
    let source_type: String
    let status: SiteStatus
    let is_multi_location: Bool
    let published_at: String?
    let created_at: String
    let updated_at: String
    let page_count: Int?

    /// The tenant's public URL — custom domain if set, else the subdomain.
    var publicURLString: String? {
        if let custom_domain, !custom_domain.isEmpty {
            return "https://\(custom_domain)"
        }
        if let subdomain, !subdomain.isEmpty {
            return "https://\(subdomain).gummfit.com"
        }
        return nil
    }
}

/// Mirrors CappeSiteCreate (server/app/cappe/models/sites.py:44-49). No page
/// editor in this app (plan §"No page editor") — always a blank site.
struct CappeSiteCreate: Encodable {
    let name: String
    let source_type: String = "blank"
    let is_multi_location: Bool = false
}

/// Mirrors CappeReadinessItem/CappeReadiness (types.ts:35-47).
struct CappeReadinessItem: Codable, Identifiable, Equatable {
    var id: String { key }
    let key: String
    let label: String
    let hint: String
    let done: Bool
    let required: Bool
    let action: String?
}

struct CappeReadiness: Codable, Equatable {
    let ready: Bool
    let items: [CappeReadinessItem]
}

/// Mirrors the owner-side taxonomy entries embedded in CappeDirectoryListing
/// (types.ts:127-134: `{ slug: string; label: string }[]`).
struct CappeDirectoryCategoryOption: Codable, Identifiable, Equatable {
    var id: String { slug }
    let slug: String
    let label: String
}

/// Mirrors CappeDirectoryListing (types.ts:121-134).
struct CappeDirectoryListing: Codable, Equatable {
    var listed: Bool
    var category: String?
    var category_label: String?
    var tags: [String]
    var blurb: String?
    let confirmed_at: String?
    let visible: Bool
    let blocked: Bool
    let categories: [CappeDirectoryCategoryOption]
}

/// Mirrors CappeDirectoryListingUpdate (server/app/cappe/models/sites.py:145-151)
/// — true PATCH semantics via `model_fields_set`. Swift's synthesized
/// Encodable omits nil Optional properties from the JSON body (calls
/// `encodeIfPresent`), so a nil field here is genuinely absent on the wire,
/// not sent as `null` — matching the server's "only what's set" contract.
struct CappeDirectoryListingUpdate: Encodable {
    var listed: Bool? = nil
    var category: String? = nil
    var tags: [String]? = nil
    var blurb: String? = nil
}
