import XCTest
@testable import Gummfit

/// Pins the login-failure dispatch to the server's actual strings
/// (server/app/cappe/routes/auth.py:210-229): 401 = wrong email/password,
/// 403 "Account is not active" = suspended, 403 "confirm your email…" =
/// unverified ⇒ verify screen.
@MainActor
final class AuthErrorMappingTests: XCTestCase {
    func testWrongPassword401ShowsError() {
        let action = AuthViewModel.loginFailureAction(status: 401, detail: "Incorrect email or password")
        XCTAssertEqual(action, .showError("Incorrect email or password"))
    }

    func testUnverified403RoutesToVerifyPending() {
        let action = AuthViewModel.loginFailureAction(
            status: 403,
            detail: "Please confirm your email before signing in. Check your inbox for the link."
        )
        XCTAssertEqual(action, .verifyPending)
    }

    func testSuspended403ShowsError() {
        let action = AuthViewModel.loginFailureAction(status: 403, detail: "Account is not active")
        XCTAssertEqual(action, .showError("Account is not active"))
    }

    func testOtherStatusPassesDetailThrough() {
        let action = AuthViewModel.loginFailureAction(status: 429, detail: "Too many attempts")
        XCTAssertEqual(action, .showError("Too many attempts"))
    }
}

final class EnumFallbackTests: XCTestCase {
    func testKnownAccountTypesDecode() throws {
        XCTAssertEqual(try JSONDecoder().decode(AccountType.self, from: Data("\"business\"".utf8)), .business)
        XCTAssertEqual(try JSONDecoder().decode(AccountType.self, from: Data("\"personal\"".utf8)), .personal)
        XCTAssertEqual(try JSONDecoder().decode(AccountType.self, from: Data("\"creator\"".utf8)), .creator)
    }

    func testUnknownAccountTypeFallsBackNotThrows() throws {
        let decoded = try JSONDecoder().decode(AccountType.self, from: Data("\"franchise\"".utf8))
        XCTAssertEqual(decoded, .unknown)
    }
}
