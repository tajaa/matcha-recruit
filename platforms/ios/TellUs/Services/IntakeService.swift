import Foundation

final class IntakeService {
    static let shared = IntakeService()
    private let client = APIClient.shared
    private init() {}

    /// GET /i/{token}. Server 404/410s on revoked/expired/exhausted links —
    /// the FastAPI detail text is user-appropriate and surfaces verbatim.
    func config(token: String) async throws -> IntakeConfig {
        try await client.request(method: "GET", path: "/i/\(token)")
    }

    func presign(token: String, _ req: MediaPresignRequest) async throws -> MediaPresignResponse {
        try await client.request(method: "POST", path: "/i/\(token)/media/presign", body: req)
    }

    /// Bearer is auto-attached by APIClient when the caller is logged in ⇒
    /// the submission is attributed (points awarded, no anonymous path
    /// needed since the app requires auth before reaching Scan).
    func submit(token: String, _ body: IntakeSubmission) async throws -> FeedbackSubmitResponse {
        try await client.request(method: "POST", path: "/i/\(token)", body: body)
    }
}
