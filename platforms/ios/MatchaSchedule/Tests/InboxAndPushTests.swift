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

    func testThreadReadsOldestFirstWhateverTheServerOrder() throws {
        func message(_ id: String, _ at: String) -> String {
            #"{"id":"\#(id)","conversation_id":"c","sender_id":"s","sender_name":"Ava","content":"\#(id)","attachments":[],"created_at":"\#(at)","edited_at":null}"#
        }
        // The server pages newest first.
        let json = "[" + [
            message("c", "2026-09-23T10:02:00.500000+00:00"),
            message("b", "2026-09-23T10:01:00Z"),
            message("a2", "2026-09-23T10:00:00Z"),
            message("a1", "2026-09-23T10:00:00Z"),
        ].joined(separator: ",") + "]"
        let messages = try JSONDecoder().decode([MWInboxMessage].self, from: Data(json.utf8))
        XCTAssertEqual(DMOrder.chronological(messages).map(\.id), ["a1", "a2", "b", "c"])
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
        // A break starting is about the shift, not a request.
        XCTAssertEqual(PushRoute.destination(for: [
            "type": "schedule_break_reminder", "link": "matchaschedule://schedule",
        ]), .schedule)
        XCTAssertEqual(PushRoute.destination(for: ["type": "inbox_message", "metadata": ["conversation_id": id]]), .inbox(id))
        XCTAssertNil(PushRoute.destination(for: ["type": "inbox_message", "metadata": ["conversation_id": "../bad"]]))
        XCTAssertEqual(PushRoute.destination(for: URL(string: "matchaschedule://requests/\(id)")!), .requests)
    }

    @MainActor
    func testSignOutRevokesTheDeviceEvenWithAnExpiredAccessToken() async throws {
        // An idle session: no live access token, only the stored refresh
        // token. Sign-out must still reach /auth/mobile/logout, and must not
        // start with a call that needs an access token.
        RecordingProtocol.requests = []
        URLProtocol.registerClass(RecordingProtocol.self)
        defer {
            URLProtocol.unregisterClass(RecordingProtocol.self)
            KeychainHelper.delete(key: KeychainHelper.Keys.refreshToken)
            KeychainHelper.delete(key: KeychainHelper.Keys.pendingRevoke)
        }
        XCTAssertTrue(KeychainHelper.save(key: KeychainHelper.Keys.refreshToken, value: "stored-refresh"))
        APIClient.shared.accessToken = nil

        let state = AppState()
        await state.signOut()

        let paths = RecordingProtocol.requests.compactMap { $0.url?.path }
        XCTAssertEqual(paths.filter { $0.hasSuffix("/auth/mobile/logout") }.count, 1, "\(paths)")
        XCTAssertFalse(paths.contains { $0.hasSuffix("/push/unregister") }, "\(paths)")
        let body = RecordingProtocol.requests.first { $0.url?.path.hasSuffix("/auth/mobile/logout") == true }
            .flatMap(RecordingProtocol.body(of:)) ?? Data()
        XCTAssertTrue(String(decoding: body, as: UTF8.self).contains("stored-refresh"))
        XCTAssertNil(KeychainHelper.load(key: KeychainHelper.Keys.refreshToken))
        if case .signedOut = state.phase {} else { XCTFail("expected signed out") }
    }
}

/// Answers every request with 200 {} and records it.
final class RecordingProtocol: URLProtocol {
    static var requests: [URLRequest] = []

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    static func body(of request: URLRequest) -> Data? {
        if let body = request.httpBody { return body }
        guard let stream = request.httpBodyStream else { return nil }
        stream.open(); defer { stream.close() }
        var data = Data()
        var buffer = [UInt8](repeating: 0, count: 4096)
        while stream.hasBytesAvailable {
            let read = stream.read(&buffer, maxLength: buffer.count)
            if read <= 0 { break }
            data.append(buffer, count: read)
        }
        return data
    }

    override func startLoading() {
        Self.requests.append(request)
        let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil,
                                       headerFields: ["Content-Type": "application/json"])!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data("{}".utf8))
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
}
