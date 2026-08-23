import Foundation

struct ShoutoutOfferPreview: Codable, Equatable {
    let brand_name: String
    let brand_logo_url: String?
    let store_name: String?
    let reward_text: String
    let offer_terms: String?
    let short_code: String
    let claim_expires_at: String
    let available: Bool
    let already_claimed: Bool
    let card_token: String?
}

struct ShoutoutOfferClaimResult: Codable {
    let offer_id: String
    let card_token: String
    let reward_text: String
    let store_name: String?
    let claim_expires_at: String
    let created: Bool
}
