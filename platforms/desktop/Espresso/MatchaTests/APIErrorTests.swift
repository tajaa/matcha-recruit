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
}
