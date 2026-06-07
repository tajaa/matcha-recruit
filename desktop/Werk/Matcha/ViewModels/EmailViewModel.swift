import Foundation
import AppKit

/// Shared so the sidebar section and the detail pane read the same loaded
/// inbox. OAuth completes in the system browser (the backend callback returns
/// a popup-closing HTML page, not a redirect to a registered URL scheme), so
/// after opening the consent URL we poll `/status` until the token lands.
@Observable
@MainActor
final class EmailViewModel {
    static let shared = EmailViewModel()

    var connected = false
    var email: String?
    var emails: [EmailMessage] = []
    var isLoading = false
    var isConnecting = false
    var errorMessage: String?

    private let service = EmailService.shared

    private init() {}

    func loadStatus() async {
        do {
            let st = try await service.status()
            connected = st.connected
            email = st.email
            if st.connected { await loadInbox() }
        } catch {
            // A failing status check just means "not connected" for our purposes.
            connected = false
        }
    }

    func connect() async {
        guard !isConnecting else { return }
        isConnecting = true
        errorMessage = nil
        defer { isConnecting = false }
        do {
            let resp = try await service.connect()
            guard let url = URL(string: resp.authUrl) else {
                errorMessage = "Couldn't open the Google sign-in page."
                return
            }
            SafeURL.open(url)
            // Poll status (~90s) waiting for the browser OAuth to finish.
            for _ in 0..<45 {
                try? await Task.sleep(nanoseconds: 2_000_000_000)
                if let st = try? await service.status(), st.connected {
                    connected = true
                    email = st.email
                    await loadInbox()
                    return
                }
            }
            errorMessage = "Timed out waiting for Gmail. Try again."
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func loadInbox() async {
        guard connected else { return }
        isLoading = true
        defer { isLoading = false }
        do {
            let resp = try await service.fetch()
            emails = resp.emails
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func disconnect() async {
        try? await service.disconnect()
        connected = false
        email = nil
        emails = []
        errorMessage = nil
    }

    func message(id: String) -> EmailMessage? {
        emails.first { $0.id == id }
    }
}
