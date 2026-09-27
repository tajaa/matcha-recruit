import XCTest
@testable import Matcha

final class CodexProtocolTests: XCTestCase {
    func testBundledRuntimeRoundTripAndRestart() async throws {
        let helper = Bundle.main.bundleURL.appendingPathComponent("Contents/Helpers/codex")
        guard FileManager.default.isExecutableFile(atPath: helper.path) else {
            throw XCTSkip("Fetch the pinned runtime to exercise the sandboxed child.")
        }
        let bridge = CodexBridge()
        // Fresh credential namespace: never read or modify a person's sign-in.
        let user = UUID().uuidString
        // The namespace lives in the real app container; don't leave one per run.
        defer { try? FileManager.default.removeItem(at: CodexBridge.home(for: user)) }
        do {
            _ = try await bridge.start(userID: user)
            let first = try await bridge.request("account/read")
            XCTAssertEqual(first["account"], .null)
            let serving = await bridge.isServing(userID: user)
            let servingOther = await bridge.isServing(userID: UUID().uuidString)
            XCTAssertTrue(serving, "an idle token-less child is reusable for account checks")
            XCTAssertFalse(servingOther, "never another Matcha user's credential home")
            _ = try await bridge.start(userID: user, token: "mat_at_test")
            let servingWithToken = await bridge.isServing(userID: user)
            XCTAssertFalse(servingWithToken, "a run's bearer-carrying child is never reused")
            _ = try await bridge.start(userID: user)
            async let one = bridge.request("account/read")
            async let two = bridge.request("account/read")
            let results = try await [one, two]
            XCTAssertTrue(results.allSatisfy { $0["account"] == .null })
            await bridge.stop()
            let servingAfterStop = await bridge.isServing(userID: user)
            XCTAssertFalse(servingAfterStop)
            do {
                _ = try await bridge.request("account/read")
                XCTFail("Stopped bridge must fail immediately")
            } catch { }
        } catch {
            await bridge.stop()
            throw error
        }
    }

    func testFragmentedUnicodeAndMultipleMessages() throws {
        var framer = CodexLineFramer()
        let bytes = Data("{\"id\":\"two\",\"result\":\"☕️\"}\n{\"id\":\"one\",\"result\":null}\n".utf8)
        var messages: [CodexJSON] = []
        for byte in bytes { messages += try framer.append(Data([byte])) }
        XCTAssertEqual(messages.count, 2)
        XCTAssertEqual(messages[0]["result"].string, "☕️")
        XCTAssertEqual(messages[1]["id"].string, "one")
    }

    func testMalformedAndOversizedLinesFailClosed() {
        var framer = CodexLineFramer()
        XCTAssertThrowsError(try framer.append(Data("not json\n".utf8)))
        framer = CodexLineFramer()
        XCTAssertThrowsError(try framer.append(Data(repeating: 32, count: CodexLineFramer.maximumBytes + 1)))
    }

    func testUnknownEventsAndJSONRoundTrip() throws {
        let message: CodexJSON = .object(["method": .string("future/event"), "params": .array([.bool(false), .number(3), .null])])
        XCTAssertEqual(try JSONDecoder().decode(CodexJSON.self, from: JSONEncoder().encode(message)), message)
    }

    private func item(status: String = "completed", task: String = "abc", attached: Bool = true, column: String = "review") -> CodexJSON {
        .object(["type": .string("mcpToolCall"), "server": .string("matcha"), "tool": .string("attach_research_report"),
                 "status": .string(status), "result": .object(["structuredContent": .object([
                    "task_id": .string(task), "attached": .bool(attached), "column": .string(column), "filename": .string("research-report-abc-r1.md")])])])
    }

    func testPublicationRequiresSuccessfulMatchingToolResult() {
        XCTAssertEqual(CodexPublication.filename(item: item(), taskID: "abc"), "research-report-abc-r1.md")
        XCTAssertNil(CodexPublication.filename(item: item(status: "failed"), taskID: "abc"))
        XCTAssertNil(CodexPublication.filename(item: item(task: "other"), taskID: "abc"))
        XCTAssertNil(CodexPublication.filename(item: item(attached: false), taskID: "abc"))
        XCTAssertNil(CodexPublication.filename(item: item(column: "in_progress"), taskID: "abc"))
        XCTAssertNil(CodexPublication.filename(item: .object(["status": .string("completed")]), taskID: "abc"))
    }

    private func delta(_ text: String, thread: String = "t1") -> CodexJSON {
        .object(["threadId": .string(thread), "itemId": .string("i"), "delta": .string(text)])
    }

    func testDeltasCoalesceIntoOneEventPerFlush() {
        var buffer = CodexDeltaCoalescer()
        for piece in ["Res", "ear", "ch ☕️"] { XCTAssertNil(buffer.append(delta(piece))) }
        let batch = buffer.take()
        XCTAssertEqual(batch?["method"].string, CodexDeltaCoalescer.method)
        XCTAssertEqual(batch?["params"]["delta"].string, "Research ☕️")
        XCTAssertEqual(batch?["params"]["threadId"].string, "t1")
        XCTAssertNil(buffer.take(), "a flush empties the batch")
        XCTAssertNil(buffer.append(.object(["threadId": .string("t1")])), "no delta text is ignored")
        XCTAssertNil(buffer.take())
    }

    func testThreadSwitchFlushesThePreviousThreadFirst() {
        var buffer = CodexDeltaCoalescer()
        _ = buffer.append(delta("old", thread: "a"))
        let flushed = buffer.append(delta("new", thread: "b"))
        XCTAssertEqual(flushed?["params"]["threadId"].string, "a")
        XCTAssertEqual(flushed?["params"]["delta"].string, "old")
        XCTAssertEqual(buffer.take()?["params"]["threadId"].string, "b")
    }

    func testOnlyEventsTheCoordinatorHandlesAreForwarded() {
        let forwarded = CodexBridge.forwardedMethods
        for method in ["account/login/completed", "item/started", "item/completed", "turn/completed", CodexDeltaCoalescer.method] {
            XCTAssertTrue(forwarded.contains(method), method)
        }
        for noisy in ["item/reasoning/textDelta", "item/commandExecution/outputDelta", "thread/tokenUsage/updated"] {
            XCTAssertFalse(forwarded.contains(noisy), noisy)
        }
    }

    func testTextEncodedMCPResult() {
        let result: CodexJSON = .object(["type": .string("mcpToolCall"), "server": .string("matcha"),
            "tool": .string("attach_research_report"), "status": .string("completed"),
            "result": .object(["content": .array([.object(["type": .string("text"),
                "text": .string("{\"task_id\":\"abc\",\"attached\":true,\"column\":\"review\",\"filename\":\"report.md\"}")])])])])
        XCTAssertEqual(CodexPublication.filename(item: result, taskID: "abc"), "report.md")
    }
}
