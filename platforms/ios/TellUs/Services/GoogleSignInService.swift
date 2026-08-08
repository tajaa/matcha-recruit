import UIKit
import GoogleSignIn

@MainActor
enum GoogleSignInService {
    struct Cancelled: Error {}
    struct NoIDToken: Error {}

    /// Presents Google's sign-in sheet and returns the ID token to hand to
    /// the backend. Throws `Cancelled` when the user backs out — callers
    /// should treat that as silent, not an error banner.
    static func presentAndFetchIDToken() async throws -> String {
        guard let presenter = topViewController() else { throw NoIDToken() }
        do {
            let result = try await GIDSignIn.sharedInstance.signIn(withPresenting: presenter)
            guard let idToken = result.user.idToken?.tokenString else { throw NoIDToken() }
            return idToken
        } catch let error as NSError where error.domain == kGIDSignInErrorDomain
            && error.code == GIDSignInError.canceled.rawValue {
            throw Cancelled()
        }
    }

    private static func topViewController() -> UIViewController? {
        UIApplication.shared.connectedScenes
            .compactMap { $0 as? UIWindowScene }
            .first { $0.activationState == .foregroundActive }?
            .keyWindow?
            .rootViewController
    }
}
