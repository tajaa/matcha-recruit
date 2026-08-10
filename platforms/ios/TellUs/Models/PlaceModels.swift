import Foundation

// Mirrors server/app/tellus/models/tellus.py TellusPlaceSearchResult /
// TellusPlaceAutocompleteResult / TellusPlaceCreate / TellusPlaceCreateResponse.

struct PlaceSearchResult: Codable, Identifiable, Hashable {
    let slug: String
    let name: String
    let logo_url: String?
    let city: String?
    let state: String?
    let claimed: Bool
    let intake_token: String?      // only ever set for unclaimed places
    let review_count: Int
    let google_place_id: String?   // lets the client dedupe vs live Google suggestions
    let messaging_enabled: Bool
    var id: String { slug }

    enum CodingKeys: String, CodingKey {
        case slug, name, logo_url, city, state, claimed, intake_token,
             review_count, google_place_id, messaging_enabled
    }

    init(slug: String, name: String, logo_url: String?, city: String?, state: String?,
         claimed: Bool, intake_token: String?, review_count: Int,
         google_place_id: String?, messaging_enabled: Bool = false) {
        self.slug = slug
        self.name = name
        self.logo_url = logo_url
        self.city = city
        self.state = state
        self.claimed = claimed
        self.intake_token = intake_token
        self.review_count = review_count
        self.google_place_id = google_place_id
        self.messaging_enabled = messaging_enabled
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        slug = try c.decode(String.self, forKey: .slug)
        name = try c.decode(String.self, forKey: .name)
        logo_url = try c.decodeIfPresent(String.self, forKey: .logo_url)
        city = try c.decodeIfPresent(String.self, forKey: .city)
        state = try c.decodeIfPresent(String.self, forKey: .state)
        claimed = try c.decode(Bool.self, forKey: .claimed)
        intake_token = try c.decodeIfPresent(String.self, forKey: .intake_token)
        review_count = try c.decode(Int.self, forKey: .review_count)
        google_place_id = try c.decodeIfPresent(String.self, forKey: .google_place_id)
        messaging_enabled = try c.decodeIfPresent(Bool.self, forKey: .messaging_enabled) ?? false
    }
}

struct PlaceSuggestion: Codable, Identifiable, Hashable {
    let place_id: String
    let name: String
    let secondary_text: String?
    var id: String { place_id }
}

struct PlaceCreateRequest: Encodable {
    let name: String
    var city: String? = nil
    var state: String? = nil
    var google_place_id: String? = nil
    var session_token: String? = nil
    var website: String? = nil     // honeypot — never populate
}

struct PlaceCreateResponse: Decodable {
    let slug: String
    let name: String
    let claimed: Bool
    let intake_token: String?
    let existing: Bool
}
