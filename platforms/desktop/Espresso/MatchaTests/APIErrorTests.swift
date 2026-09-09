import XCTest
@testable import Matcha

/// Covers the user-facing error mapping added when swallowed errors were
/// surfaced. A wrong branch here is what turns a deploy window into a raw
/// HTML blob rendered in an alert.
final class APIErrorTests: XCTestCase {

    // MARK: - 5xx HTML collapse

    func testHTTPErrorWithHTMLBodyCollapsesToMaintenanceCopy() {
        for body in ["<!DOCTYPE html><html>...", "  <html><body>502 Bad Gateway</body></html>"] {
            let description = APIError.httpError(502, body).errorDescription
            XCTAssertEqual(description, "Server is updating. Try again in 30 seconds.",
                           "an HTML 5xx body must never reach the user verbatim")
        }
    }

    func testHTTPErrorWithJSONBodyKeepsItsMessage() {
        let description = APIError.httpError(500, "{\"detail\":\"boom\"}").errorDescription
        XCTAssertEqual(description, "HTTP 500: {\"detail\":\"boom\"}")
    }

    func testFourXXWithHTMLBodyIsNotCollapsed() {
        // The collapse is deliberately 5xx-only; a 404 HTML body is a routing
        // bug worth seeing, not a maintenance window.
        let description = APIError.httpError(404, "<html>not found</html>").errorDescription
        XCTAssertEqual(description, "HTTP 404: <html>not found</html>")
    }

    // MARK: - serviceUnavailable

    func testGatewayCodesGetRetryCopy() {
        for code in [502, 503, 504] {
            XCTAssertEqual(APIError.serviceUnavailable(code).errorDescription,
                           "Server is updating. Try again in 30 seconds.")
        }
    }

    func testOtherServerCodesGetGenericCopy() {
        XCTAssertEqual(APIError.serviceUnavailable(500).errorDescription,
                       "Server error (500). Try again in a moment.")
    }

    // MARK: - networkUnavailable

    func testNetworkErrorCopyPerURLErrorCode() {
        let cases: [(URLError.Code, String)] = [
            (.notConnectedToInternet, "No internet connection. Reconnect and try again."),
            (.timedOut, "Request timed out. Try again."),
            (.cannotFindHost, "Couldn't reach the server. Check your network and try again."),
            (.dnsLookupFailed, "Couldn't reach the server. Check your network and try again."),
            (.cannotConnectToHost, "Lost connection to the server. Try again."),
            (.networkConnectionLost, "Lost connection to the server. Try again."),
            (.badServerResponse, "Network error. Try again."),
        ]
        for (code, expected) in cases {
            XCTAssertEqual(APIError.networkUnavailable(URLError(code)).errorDescription, expected,
                           "wrong copy for \(code)")
        }
    }

    // MARK: - Simple cases

    func testStaticCaseCopy() {
        XCTAssertEqual(APIError.unauthorized.errorDescription, "Unauthorized — please log in again")
        XCTAssertEqual(APIError.invalidURL.errorDescription, "Invalid URL")
        XCTAssertEqual(APIError.noData.errorDescription, "No data received")
    }

    /// `localizedDescription` on a `LocalizedError` must route through
    /// `errorDescription` — the views display the former.
    func testLocalizedDescriptionRoutesThroughErrorDescription() {
        XCTAssertEqual(APIError.noData.localizedDescription, "No data received")
    }

    // MARK: - Cancellation classification

    /// Cancellations are ordinary teardown (a view disappearing mid-request),
    /// not failures — misclassifying them is what produced spurious error
    /// banners once errors stopped being swallowed.
    func testIsCancellationRecognizesBothCancellationShapes() {
        XCTAssertTrue(CancellationError().isCancellation)
        XCTAssertTrue(URLError(.cancelled).isCancellation)
    }

    func testIsCancellationRejectsRealFailures() {
        XCTAssertFalse(URLError(.timedOut).isCancellation)
        XCTAssertFalse(APIError.unauthorized.isCancellation)
        XCTAssertFalse(APIError.httpError(500, "boom").isCancellation)
    }

    // MARK: - "Is the mailbox connected?" is the server's verdict, not a word

    /// The staged-outreach row swaps **Retry send** for **Connect Gmail to
    /// send** when the mailbox is not connected. Deciding that by looking for
    /// "gmail" anywhere in the message matched every failure that came back
    /// FROM Gmail — `GMAIL_API_BASE` is `gmail.googleapis.com`, so httpx puts
    /// the host in the text of a 429 or a transient 503 and the route re-raises
    /// it verbatim. The approver then lost the Retry button on a perfectly
    /// connected mailbox, and it never came back: the status is re-read only
    /// while it is still unknown.
    func testOnlyTheServersOwnNotConnectedVerdictClearsTheGmailFlag() {
        XCTAssertTrue(TaskViewerSheet.isGmailNotConnected(APIError.httpError(
            400, "Connect your Gmail before approving a send — mail goes out from your own mailbox")))
    }

    func testAnErrorReturnedByGmailDoesNotMeanGmailIsDisconnected() {
        let fromGmail = [
            "Send failed: Client error '429 Too Many Requests' for url 'https://gmail.googleapis.com/gmail/v1/users/me/messages/send'",
            "Send failed: Server error '503 Service Unavailable' for url 'https://gmail.googleapis.com/gmail/v1/users/me/messages/send'",
        ]
        for message in fromGmail {
            XCTAssertFalse(TaskViewerSheet.isGmailNotConnected(APIError.httpError(502, message)),
                           "a failure from Gmail says nothing about whether the mailbox is connected")
        }
        // Right sentence, wrong status: only the pre-flight 400 is the verdict.
        XCTAssertFalse(TaskViewerSheet.isGmailNotConnected(
            APIError.httpError(500, "Connect your Gmail")))
    }
}

/// Lives here rather than in its own file only because adding one would mean
/// hand-editing `project.pbxproj`; it is otherwise unrelated to APIError.
final class JournalBlockParseTests: XCTestCase {

    /// The pipe-table run is emitted by `flushTable()`, which every non-table
    /// line reaches — except the three fence branches, which `continue` first.
    /// A fence opened straight after a table therefore appended its code block
    /// while the table was still buffered, so the table rendered BELOW the code
    /// that followed it. Research reports, this lane's own deliverable, put
    /// code samples under comparison tables routinely.
    func testACodeFenceAfterATableRendersBelowIt() {
        let blocks = JournalBlockParser.parse("""
        | Region | Cost |
        |---|---|
        ```
        let x = 1
        ```
        done
        """)
        let code = blocks.firstIndex(where: { block in
            if case .codeBlock(let s) = block { return s == "let x = 1" }
            return false
        })
        let table = blocks.firstIndex(where: { block in
            if case .codeBlock(let s) = block { return s.contains("| Region | Cost |") }
            return false
        })
        XCTAssertNotNil(table, "the table must still be emitted")
        XCTAssertNotNil(code)
        XCTAssertLessThan(table!, code!, "the table comes first in the source and must render first")
    }

    /// The `table / fence / table` shape is what merged both tables into one
    /// block placed after the code.
    func testTwoTablesSeparatedByAFenceStaySeparate() {
        let blocks = JournalBlockParser.parse("""
        | a |
        |---|
        ```
        code
        ```
        | b |
        |---|
        """)
        let tables = blocks.filter({ block -> Bool in
            if case .codeBlock(let s) = block { return s.hasPrefix("|") }
            return false
        })
        XCTAssertEqual(tables.count, 2, "each table is its own block")
    }
}
