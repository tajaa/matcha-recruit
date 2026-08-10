import XCTest
@testable import Gummfit

final class MarketingCreatorDecodeTests: XCTestCase {
    func testCampaignDecodesNullableFields() throws {
        let data = Data(#"{"id":"c","site_id":"s","subject":"Hello","body_html":null,"from_name":null,"status":"draft","scheduled_at":null,"sent_at":null,"recipient_count":0,"created_at":"now","updated_at":"now"}"#.utf8)
        XCTAssertEqual(try JSONDecoder().decode(CappeCampaign.self, from: data).subject, "Hello")
    }
    func testEarningsUsesStableCompositeIdentity() {
        let row = EarningsRow(offer_id: "offer", offer_title: "Deal", brand_name: nil, label: "Upfront", amount_cents: 1234, fee_cents: nil, status: "paid", paid_at: nil)
        XCTAssertEqual(row.id, "offer-Upfront")
    }
}
