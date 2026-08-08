import XCTest
@testable import TellUs

@MainActor
final class AuthErrorMappingTests: XCTestCase {
    func testSuspended403ShowsError() {
        XCTAssertEqual(
            AuthViewModel.loginFailureAction(status: 403, detail: "Account is not active"),
            .showError("Account is not active")
        )
    }

    func testUnverified403GoesVerify() {
        XCTAssertEqual(
            AuthViewModel.loginFailureAction(
                status: 403,
                detail: "Please confirm your email before signing in. Check your inbox for the link."
            ),
            .verifyPending
        )
    }

    func test401ShowsServerDetail() {
        XCTAssertEqual(
            AuthViewModel.loginFailureAction(status: 401, detail: "Incorrect email or password"),
            .showError("Incorrect email or password")
        )
    }

    func testOtherStatusPassthrough() {
        XCTAssertEqual(
            AuthViewModel.loginFailureAction(status: 500, detail: "boom"),
            .showError("boom")
        )
    }
}
