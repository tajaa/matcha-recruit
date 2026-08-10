import XCTest
@testable import TellUs

final class CommsModelDecodeTests: XCTestCase {
    func testLegacyThreadDefaultsToFeedback() throws {
        let json = #"{"id":"t1","counterparty_name":"Acme","blocked":false,"unread_count":0,"last_message_at":"2026-01-01T00:00:00Z","created_at":"2026-01-01T00:00:00Z"}"#
        let thread = try JSONDecoder().decode(DmThread.self, from: Data(json.utf8))
        XCTAssertEqual(thread.kind, .feedback)
        XCTAssertEqual(thread.status, .waiting_consumer)
        XCTAssertNil(thread.report_id)
    }

    func testGeneralThreadDecodesRoutingFields() throws {
        let json = #"{"id":"t1","report_id":null,"counterparty_name":"Acme","report_title":null,"report_number":null,"review_state":null,"publish_at":null,"blocked":false,"unread_count":1,"last_message_at":"2026-01-01T00:00:00Z","created_at":"2026-01-01T00:00:00Z","kind":"general","topic":"availability","status":"waiting_brand","store_id":"s1","store_name":"Main","store_city":"Austin","assigned_member_id":null,"assigned_member_name":null,"viewer_role":"consumer","first_brand_response_at":null,"closed_at":null}"#
        let thread = try JSONDecoder().decode(DmThread.self, from: Data(json.utf8))
        XCTAssertEqual(thread.kind, .general)
        XCTAssertEqual(thread.topic, .availability)
        XCTAssertEqual(thread.viewer_role, .consumer)
        XCTAssertEqual(thread.store_name, "Main")
    }

    func testCommsStartRequestIncludesStableClientID() throws {
        let request = CommsStartRequest(
            storeID: "store-1", topic: .hours, body: "Are you open tomorrow?",
            clientMessageId: "message-1"
        )
        let data = try JSONEncoder().encode(request)
        let json = String(data: data, encoding: .utf8)!
        XCTAssertTrue(json.contains("\"store_id\":\"store-1\""))
        XCTAssertTrue(json.contains("\"topic\":\"hours\""))
        XCTAssertTrue(json.contains("\"client_message_id\":\"message-1\""))
    }
}
