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
    var id: String { slug }
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
