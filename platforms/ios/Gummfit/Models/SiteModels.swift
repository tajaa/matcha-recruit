import Foundation

/// Mirrors server/app/cappe/models/sites.py + client/src/cappe/types.ts:51-80.
/// Extra wire fields are ignored by JSONDecoder, so this remains compatible
/// with older site payloads while exposing the settings needed by iOS.
struct CappeSite: Codable, Identifiable, Equatable {
    let id: String
    let account_id: String
    let name: String
    let slug: String
    let subdomain: String?
    let custom_domain: String?
    let source_type: String
    let status: SiteStatus
    let timezone: String?
    let theme_config: CappeThemeConfig?
    let is_multi_location: Bool
    let tax_rate_bps: Int?
    let tax_label: String?
    let shipping_flat_cents: Int?
    let shipping_free_threshold_cents: Int?
    let shipping_label: String?
    let receipt_prefix: String?
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

/// Mirrors CappeSiteCreate (server/app/cappe/models/sites.py:44-49).
struct CappeSiteCreate: Encodable {
    let name: String
    let source_type: String = "blank"
    let is_multi_location: Bool = false
}
struct CappeSiteUpdate: Encodable {
    var name, subdomain, timezone, tax_label, shipping_label, receipt_prefix: String?
    var status: String?
    var theme_config: [String: JSONValue]? = nil
    var meta_config: [String: JSONValue]? = nil
    var tax_rate_bps, shipping_flat_cents, shipping_free_threshold_cents: Int?
    var is_multi_location: Bool?

    private enum CodingKeys: String, CodingKey {
        case name, subdomain, timezone, tax_label, shipping_label, receipt_prefix, status, theme_config, meta_config
        case tax_rate_bps, shipping_flat_cents, shipping_free_threshold_cents, is_multi_location
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encodeIfPresent(name, forKey: .name)
        try container.encodeIfPresent(subdomain, forKey: .subdomain)
        try container.encodeIfPresent(timezone, forKey: .timezone)
        try container.encodeIfPresent(tax_label, forKey: .tax_label)
        try container.encodeIfPresent(shipping_label, forKey: .shipping_label)
        try container.encode(receipt_prefix, forKey: .receipt_prefix)
        try container.encodeIfPresent(status, forKey: .status)
        try container.encodeIfPresent(theme_config, forKey: .theme_config)
        try container.encodeIfPresent(meta_config, forKey: .meta_config)
        try container.encodeIfPresent(tax_rate_bps, forKey: .tax_rate_bps)
        try container.encodeIfPresent(shipping_flat_cents, forKey: .shipping_flat_cents)
        // The API uses an explicit null to clear these optional settings.
        try container.encode(shipping_free_threshold_cents, forKey: .shipping_free_threshold_cents)
        try container.encodeIfPresent(is_multi_location, forKey: .is_multi_location)
    }
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
