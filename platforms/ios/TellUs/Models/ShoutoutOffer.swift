import Foundation

private let shoutoutCodeAlphabet = CharacterSet(charactersIn: "0123456789ABCDEFGHJKMNPQRSTVWXYZ")

func normalizeShoutoutCode(_ raw: String) -> String? {
    let code = raw.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
    guard code.count == 8, code.unicodeScalars.allSatisfy(shoutoutCodeAlphabet.contains) else { return nil }
    return code
}

struct ShoutoutOfferPreview: Codable, Equatable {
    let brand_name: String
    let brand_logo_url: String?
    let store_name: String?
    let reward_text: String
    let offer_terms: String?
    let short_code: String
    let claim_expires_at: String
    let available: Bool
    let require_app_install: Bool
    let web_claim_allowed: Bool
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
