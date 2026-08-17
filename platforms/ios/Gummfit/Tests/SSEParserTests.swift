import Foundation
import XCTest
@testable import Gummfit

final class SSEParserTests: XCTestCase {
    private struct Body: Encodable { let value = "test" }

    override func setUp() {
        super.setUp()
        URLProtocol.registerClass(StubURLProtocol.self)
        StubURLProtocol.statusCode = 200
        StubURLProtocol.responseBody = Data()
        StubURLProtocol.chunks = []
        APIClient.shared.accessToken = nil
    }

    override func tearDown() {
        URLProtocol.unregisterClass(StubURLProtocol.self)
        super.tearDown()
    }

    private func stream(_ chunks: [Data]) async throws -> [Data] {
        StubURLProtocol.chunks = chunks
        var frames: [Data] = []
        try await APIClient.shared.streamSSE(path: "/test", body: Body()) { frame in
            frames.append(frame)
            return frame == Data("[DONE]".utf8)
        }
        return frames
    }

    func testFrameSplitAcrossChunksAndCRLF() async throws {
        let line = Data("data: {\"message\":\"split\"}\r\n".utf8)
        let cut = line.count / 2
        let frames = try await stream([line.subdata(in: 0..<cut), line.subdata(in: cut..<line.count)])
        XCTAssertEqual(frames, [Data("{\"message\":\"split\"}".utf8)])
    }

    func testMultibyteCharacterSplitAcrossChunks() async throws {
        let line = Data("data: {\"message\":\"café 🙂\"}\n".utf8)
        let emojiByte = line.firstIndex(of: 0xF0) ?? line.count / 2
        let frames = try await stream([line.subdata(in: 0..<emojiByte + 1), line.subdata(in: emojiByte + 1..<line.count)])
        XCTAssertEqual(String(data: frames[0], encoding: .utf8), #"{"message":"café 🙂"}"#)
    }

    func testDoneAndUnterminatedTerminalFrameAreHandled() async throws {
        let frames = try await stream([
            Data(": heartbeat\n".utf8),
            Data("event: ignored\n".utf8),
            Data("data: {\"type\":\"result\"}\n".utf8),
            Data("data: [DONE]".utf8),
        ])
        XCTAssertEqual(frames, [Data("{\"type\":\"result\"}".utf8)])
    }

    func testMalformedFrameCanBeSkippedByConsumer() async throws {
        let frames = try await stream([
            Data("data: not-json\n".utf8),
            Data("data: {\"ok\":true}\n".utf8),
        ])
        let valid = frames.compactMap { try? JSONSerialization.jsonObject(with: $0) }
        XCTAssertEqual(valid.count, 1)
        XCTAssertEqual((valid[0] as? [String: Bool])?["ok"], true)
    }

    func testHTTPErrorIncludesStatusAndDetail() async {
        StubURLProtocol.statusCode = 429
        StubURLProtocol.responseBody = Data(#"{"detail":"rate limited"}"#.utf8)
        do {
            _ = try await stream([])
            XCTFail("Expected HTTP error")
        } catch let APIError.httpError(code, message) {
            XCTAssertEqual(code, 429)
            XCTAssertEqual(message, "rate limited")
        } catch {
            XCTFail("Unexpected error: \(error)")
        }
    }

    func testMerlinServiceFailsWhenNoTerminalFrameArrives() async {
        StubURLProtocol.chunks = [Data("data: not-json\n".utf8)]
        let body = CappeMerlinChatRequest(
            page_id: "p1", conversation_id: nil, message: "hello", history: [], blocks: [],
            theme: [:], model_tier: "auto", selected_block: nil, selection: nil, attachments: []
        )
        do {
            try await MerlinService.shared.agent(siteId: "s1", body) { _ in }
            XCTFail("Expected a missing terminal frame error")
        } catch APIError.noData {
            // Expected: malformed/intermediate frames cannot make a turn succeed.
        } catch {
            XCTFail("Unexpected error: \(error)")
        }
    }
}
