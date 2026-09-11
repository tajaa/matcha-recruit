import Foundation
import AppKit

/// One sidebar group. `bucket == nil` is the untriaged remainder ("Unsorted"),
/// or the whole list before the user has organized.
struct EmailGroup: Identifiable {
    let bucket: EmailTriageBucket?
    let emails: [EmailMessage]
    var id: String { bucket?.rawValue ?? "unsorted" }
}

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

    /// AI triage keyed by message id. In-app only — survives a refresh for
    /// messages still in the list; new arrivals land in "Unsorted".
    var triage: [String: EmailTriageEntry] = [:]
    var isTriaging = false

    /// Messages opened after they left the unread list (read elsewhere, or
    /// re-opened after a relaunch) — fetched one at a time by id.
    private var detailCache: [String: EmailMessage] = [:]

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
            let ids = Set(resp.emails.map(\.id))
            triage = triage.filter { ids.contains($0.key) }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func disconnect() async {
        try? await service.disconnect()
        connected = false
        email = nil
        emails = []
        triage = [:]
        detailCache = [:]
        errorMessage = nil
    }

    func message(id: String) -> EmailMessage? {
        emails.first { $0.id == id } ?? detailCache[id]
    }

    /// The loaded copy when there is one, else a one-off fetch by id.
    func ensureMessage(id: String) async -> EmailMessage? {
        if let msg = message(id: id) { return msg }
        guard connected else { return nil }
        guard let fetched = try? await service.message(id: id) else { return nil }
        detailCache[id] = fetched
        return fetched
    }

    // MARK: Organize (AI triage)

    func organize() async {
        guard connected, !emails.isEmpty, !isTriaging else { return }
        isTriaging = true
        errorMessage = nil
        defer { isTriaging = false }
        do {
            let resp = try await service.triage(emailIds: emails.map(\.id))
            triage = Dictionary(resp.buckets.map { ($0.emailId, $0) }, uniquingKeysWith: { _, new in new })
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func clearTriage() {
        triage = [:]
    }

    /// `list` grouped by triage bucket in priority order, empty groups
    /// dropped. Untriaged → a single ungrouped list.
    func grouped(_ list: [EmailMessage]) -> [EmailGroup] {
        guard !triage.isEmpty else { return [EmailGroup(bucket: nil, emails: list)] }
        var byBucket: [EmailTriageBucket: [EmailMessage]] = [:]
        var unsorted: [EmailMessage] = []
        for msg in list {
            if let bucket = triage[msg.id]?.bucket {
                byBucket[bucket, default: []].append(msg)
            } else {
                unsorted.append(msg)
            }
        }
        var groups = EmailTriageBucket.allCases.compactMap { bucket -> EmailGroup? in
            guard let msgs = byBucket[bucket], !msgs.isEmpty else { return nil }
            return EmailGroup(bucket: bucket, emails: msgs)
        }
        if !unsorted.isEmpty { groups.append(EmailGroup(bucket: nil, emails: unsorted)) }
        return groups
    }
}
