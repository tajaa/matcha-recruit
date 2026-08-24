import XCTest
@testable import TellUs

final class ShoutoutOfferModelDecodeTests: XCTestCase {
    func testOfferPreviewDecodesInstallGateFields() throws {
        let json = #"{"brand_name":"Cafe","brand_logo_url":null,"store_name":"Main","reward_text":"Coffee","offer_terms":null,"short_code":"7H2K9PQR","claim_expires_at":"2026-12-01T00:00:00Z","require_app_install":true,"web_claim_allowed":false,"available":true,"already_claimed":false,"card_token":null}"#
        let preview = try JSONDecoder().decode(ShoutoutOfferPreview.self, from: Data(json.utf8))
        XCTAssertTrue(preview.require_app_install)
        XCTAssertFalse(preview.web_claim_allowed)
        XCTAssertEqual(preview.short_code, "7H2K9PQR")
    }

    func testClaimResultDecodes() throws {
        let json = #"{"offer_id":"offer","card_token":"card","reward_text":"Coffee","store_name":"Main","claim_expires_at":"2026-12-01T00:00:00Z","created":false}"#
        let result = try JSONDecoder().decode(ShoutoutOfferClaimResult.self, from: Data(json.utf8))
        XCTAssertEqual(result.card_token, "card")
        XCTAssertFalse(result.created)
    }
}
