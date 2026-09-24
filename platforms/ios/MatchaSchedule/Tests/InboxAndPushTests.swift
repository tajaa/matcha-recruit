import XCTest
@testable import MatchaSchedule

final class InboxAndPushTests: XCTestCase {
    func testInboxSummaryAndThreadDecode() throws {
        let summary = """
        [{"id":"11111111-1111-1111-1111-111111111111","title":null,"is_group":false,
          "last_message_at":"2026-09-23T10:00:00Z","last_message_preview":"Hello",
          "participants":[{"user_id":"22222222-2222-2222-2222-222222222222","name":"Ava",
            "email":"ava@example.com","role":"employee","avatar_url":null,"last_read_at":null,"is_muted":false}],
          "unread_count":2}]
        """
        let conversations = try JSONDecoder().decode([MWInboxConversation].self, from: Data(summary.utf8))
        XCTAssertEqual(conversations[0].unreadCount, 2)
        XCTAssertEqual(DM.title(conversations[0], myId: "me"), "Ava")

        let message = """
        {"id":"33333333-3333-3333-3333-333333333333","conversation_id":"11111111-1111-1111-1111-111111111111",
         "sender_id":"22222222-2222-2222-2222-222222222222","sender_name":"Ava","content":"Hello",
         "attachments":[],"created_at":"2026-09-23T10:00:00Z","edited_at":null}
        """
        let decoded = try JSONDecoder().decode(MWInboxMessage.self, from: Data(message.utf8))
        XCTAssertEqual(decoded.content, "Hello")
    }

    func testBellNotificationAcceptsMixedMetadata() throws {
        let json = """
        {"notifications":[{"id":"11111111-1111-1111-1111-111111111111","type":"schedule_published",
          "title":"Schedule published","body":"Two shifts","link":"matchaschedule://schedule",
          "metadata":{"batch_id":"22222222-2222-2222-2222-222222222222","shift_count":2,"starts_at":null},
          "is_read":false,"created_at":"2026-09-23T10:00:00Z"}],"total":1}
        """
        let response = try JSONDecoder().decode(NotificationsResponse.self, from: Data(json.utf8))
        XCTAssertEqual(response.notifications.count, 1)
        XCTAssertFalse(response.notifications[0].is_read)
    }

    func testPushRoutesScheduleRequestsAndInbox() {
        let id = "11111111-1111-1111-1111-111111111111"
        XCTAssertEqual(PushRoute.destination(for: ["type": "schedule_published"]), .schedule)
        XCTAssertEqual(PushRoute.destination(for: ["type": "schedule_request_decided"]), .requests)
        XCTAssertEqual(PushRoute.destination(for: ["type": "inbox_message", "metadata": ["conversation_id": id]]), .inbox(id))
        XCTAssertNil(PushRoute.destination(for: ["type": "inbox_message", "metadata": ["conversation_id": "../bad"]]))
        XCTAssertEqual(PushRoute.destination(for: URL(string: "matchaschedule://requests/\(id)")!), .requests)
    }
}
