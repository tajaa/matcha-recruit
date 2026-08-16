import XCTest
@testable import TellUs

final class CampaignSheetTests: XCTestCase {
    func testDesignSheetHasDistinctIdentity() {
        let campaign = PromoCampaign(
            id: "campaign-1",
            title: "Beach day",
            description: nil,
            reward_text: "Free smoothie",
            claim_token: "claim-token",
            claim_url: "/tellus/p/claim-token",
            max_claims: 50,
            claim_count: 0,
            status: "active",
            card_expiry_days: 30,
            starts_at: nil,
            ends_at: nil,
            flyer_image_url: nil,
            has_design: false,
            cancelled_at: nil,
            created_at: "2026-08-16T00:00:00Z",
            campaign_type: "location",
            store_id: "store-1",
            store_name: "Venice",
            radius_miles: 5,
            push_sent_at: nil,
            push_sent_count: 0,
            stats: nil
        )

        XCTAssertEqual(CampaignSheet.design(campaign).id, "design-campaign-1")
        XCTAssertNotEqual(CampaignSheet.design(campaign).id, CampaignSheet.qr(campaign).id)
    }
}
