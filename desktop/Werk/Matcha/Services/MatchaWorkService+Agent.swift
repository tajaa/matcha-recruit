import Foundation

extension MatchaWorkService {
    // MARK: - Billing

    func getPersonalSubscription() async throws -> MWSubscription {
        try await client.request(method: "GET", path: "\(basePath)/billing/subscription")
    }

    func startPersonalCheckout(successUrl: String, cancelUrl: String) async throws -> String {
        struct Body: Codable {
            let successUrl: String
            let cancelUrl: String
            enum CodingKeys: String, CodingKey {
                case successUrl = "success_url"
                case cancelUrl = "cancel_url"
            }
        }
        let resp: MWCheckoutResponse = try await client.request(
            method: "POST",
            path: "\(basePath)/billing/checkout/personal",
            body: Body(successUrl: successUrl, cancelUrl: cancelUrl)
        )
        return resp.checkoutUrl
    }

    // MARK: - Email Agent

    func agentEmailStatus() async throws -> MWAgentEmailStatus {
        try await client.request(method: "GET", path: "\(basePath)/agent/email/status")
    }

    func agentConnectGmail() async throws -> String {
        struct Resp: Codable { let authUrl: String; enum CodingKeys: String, CodingKey { case authUrl = "auth_url" } }
        let resp: Resp = try await client.request(method: "POST", path: "\(basePath)/agent/email/connect")
        return resp.authUrl
    }

    func agentDisconnectGmail() async throws {
        _ = try await client.requestData(method: "DELETE", path: "\(basePath)/agent/email/disconnect")
    }

    func agentFetchEmails() async throws -> [MWAgentEmail] {
        try await client.request(method: "POST", path: "\(basePath)/agent/email/fetch")
    }

    func agentDraftReply(emailId: String, instructions: String) async throws -> String {
        struct Body: Codable { let emailId: String; let instructions: String
            enum CodingKeys: String, CodingKey { case emailId = "email_id"; case instructions }
        }
        struct Resp: Codable { let draft: String }
        let resp: Resp = try await client.request(method: "POST", path: "\(basePath)/agent/email/draft", body: Body(emailId: emailId, instructions: instructions))
        return resp.draft
    }

    func agentSendEmail(to: String, subject: String, body: String, replyToId: String? = nil) async throws {
        struct Body: Codable { let to: String; let subject: String; let body: String; let replyToId: String?
            enum CodingKeys: String, CodingKey { case to, subject, body; case replyToId = "reply_to_id" }
        }
        _ = try await client.requestData(method: "POST", path: "\(basePath)/agent/email/send", body: Body(to: to, subject: subject, body: body, replyToId: replyToId))
    }
}
