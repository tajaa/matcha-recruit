import Foundation
import AppKit

/// One list section. `bucket == nil` is the untriaged remainder ("Unsorted"),
/// or the whole list before anything has been organized.
struct EmailGroup: Identifiable {
    let bucket: EmailTriageBucket?
    let emails: [EmailMessage]
    var id: String { bucket?.rawValue ?? "unsorted" }
}

/// Display strings for one message, derived once per load — the hub's
/// columns resize live, and re-parsing an RFC 2822 date on every frame is
/// wasted work.
struct EmailRowInfo {
    let senderName: String
    let senderAddress: String
    let initial: String
    /// Index into the avatar palette; stable per sender across launches.
    let tint: Int
    let dateLabel: String
    let fullDate: String
    let preview: String
}

/// Shared so the Email hub, its reader and the email-ticket wizard read the
/// same loaded inbox. OAuth completes in the system browser (the backend
/// callback returns a popup-closing HTML page, not a redirect to a registered
/// URL scheme), so after opening the consent URL we poll `/status` until the
/// token lands.
@Observable
@MainActor
final class EmailViewModel {
    static let shared = EmailViewModel()

    var connected = false
    /// False until the first status check answers, so the hub doesn't flash
    /// its connect screen at someone who is already connected.
    var statusLoaded = false
    var email: String?
    var emails: [EmailMessage] = []
    var isLoading = false
    var isConnecting = false
    var errorMessage: String?
    /// Messages one card snapshot takes — the server's cap, from `/status`.
    var snapshotLimit = 10

    /// AI triage keyed by message id. In-app only — nothing is labelled or
    /// moved in Gmail. Survives a refresh for messages still in the list.
    var triage: [String: EmailTriageEntry] = [:]
    var isTriaging = false

    /// Single-message fetches: they carry the HTML body the list leaves out,
    /// and cover a message opened after it left the unread list. Bounded —
    /// one newsletter can be a megabyte of HTML — so only the most recently
    /// opened few stay (`fullCacheOrder`, most recent last).
    @ObservationIgnored private var fullCache: [String: EmailMessage] = [:]
    @ObservationIgnored private var fullCacheOrder: [String] = []
    private static let fullCacheLimit = 12
    @ObservationIgnored private var rowInfoCache: [String: EmailRowInfo] = [:]
    @ObservationIgnored private var lastLoadedAt: Date?

    private let service = EmailService.shared

    private init() {}

    func loadStatus() async {
        do {
            let st = try await service.status()
            connected = st.connected
            email = st.email
            if let limit = st.snapshotMaxEmails, limit > 0 { snapshotLimit = limit }
            statusLoaded = true
            if st.connected { await loadInbox() }
        } catch {
            // A failing status check just means "not connected" for our purposes.
            connected = false
            statusLoaded = true
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
        guard connected, !isLoading else { return }
        isLoading = true
        defer { isLoading = false }
        do {
            let resp = try await service.fetch()
            // Date labels are relative to now, so they're rebuilt per load.
            rowInfoCache = [:]
            emails = resp.emails
            let ids = Set(resp.emails.map(\.id))
            triage = triage.filter { ids.contains($0.key) }
            errorMessage = nil
            lastLoadedAt = Date()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    /// Reload the inbox unless it was loaded in the last `maxAge` seconds, so
    /// reopening the hub doesn't cost 25 Gmail reads every time.
    func refreshIfStale(maxAge: TimeInterval = 120) async {
        if let lastLoadedAt, Date().timeIntervalSince(lastLoadedAt) < maxAge { return }
        await loadInbox()
    }

    func disconnect() async {
        try? await service.disconnect()
        connected = false
        email = nil
        emails = []
        triage = [:]
        fullCache = [:]
        fullCacheOrder = []
        rowInfoCache = [:]
        lastLoadedAt = nil
        errorMessage = nil
    }

    func message(id: String) -> EmailMessage? {
        emails.first { $0.id == id } ?? fullCache[id]
    }

    /// The loaded copy when there is one, else a one-off fetch by id.
    func ensureMessage(id: String) async -> EmailMessage? {
        if let msg = emails.first(where: { $0.id == id }) { return msg }
        return await fullMessage(id: id)
    }

    /// The message with its HTML body (fetched once, then cached).
    func fullMessage(id: String) async -> EmailMessage? {
        if let cached = fullCache[id] {
            touchFull(id)
            return cached
        }
        guard connected, let fetched = try? await service.message(id: id) else { return nil }
        fullCache[id] = fetched
        touchFull(id)
        while fullCacheOrder.count > Self.fullCacheLimit {
            fullCache[fullCacheOrder.removeFirst()] = nil
        }
        return fetched
    }

    private func touchFull(_ id: String) {
        fullCacheOrder.removeAll { $0 == id }
        fullCacheOrder.append(id)
    }

    // MARK: Organize (AI triage)

    /// Sort whatever hasn't been sorted yet. The hub calls this on every
    /// load, so only new arrivals cost a model call.
    func organizeNew() async {
        await organize(ids: emails.map(\.id).filter { triage[$0] == nil }, replacing: false)
    }

    /// Re-sort everything. The old groups stay up until the new ones land.
    func reorganize() async {
        await organize(ids: emails.map(\.id), replacing: true)
    }

    private func organize(ids: [String], replacing: Bool) async {
        guard connected, !ids.isEmpty, !isTriaging else { return }
        isTriaging = true
        errorMessage = nil
        defer { isTriaging = false }
        do {
            let resp = try await service.triage(emailIds: Array(ids.prefix(25)))
            var next = replacing ? [:] : triage
            for entry in resp.buckets { next[entry.emailId] = entry }
            triage = next
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func clearTriage() {
        triage = [:]
    }

    func bucket(of id: String) -> EmailTriageBucket? {
        triage[id]?.bucket
    }

    func count(of bucket: EmailTriageBucket) -> Int {
        emails.reduce(0) { $0 + (triage[$1.id]?.bucket == bucket ? 1 : 0) }
    }

    var unsortedCount: Int {
        triage.isEmpty ? 0 : emails.reduce(0) { $0 + (triage[$1.id] == nil ? 1 : 0) }
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

    func rowInfo(for msg: EmailMessage) -> EmailRowInfo {
        if let cached = rowInfoCache[msg.id] { return cached }
        let date = EmailDates.parse(msg.date)
        let name = msg.senderName
        let info = EmailRowInfo(
            senderName: name,
            senderAddress: msg.senderAddress,
            initial: name.first.map { String($0).uppercased() } ?? "?",
            tint: EmailDates.stableIndex(msg.senderAddress, modulo: 8),
            dateLabel: date.map(EmailDates.listLabel) ?? "",
            fullDate: date.map(EmailDates.fullLabel) ?? msg.date,
            preview: msg.previewText
        )
        rowInfoCache[msg.id] = info
        return info
    }
}

// MARK: - Display helpers

extension EmailMessage {
    /// "Pinterest" out of `Pinterest <recs@discover.pinterest.com>`; the
    /// mailbox name when there is no display name.
    var senderName: String {
        let raw = fromAddress.trimmingCharacters(in: .whitespacesAndNewlines)
        if let lt = raw.firstIndex(of: "<"), lt > raw.startIndex {
            let name = raw[..<lt].trimmingCharacters(in: CharacterSet.whitespaces.union(CharacterSet(charactersIn: "\"'")))
            if !name.isEmpty { return name }
        }
        let address = senderAddress
        return address.split(separator: "@").first.map(String.init) ?? address
    }

    var senderAddress: String {
        if let lt = fromAddress.firstIndex(of: "<"), let gt = fromAddress.lastIndex(of: ">"), lt < gt {
            return String(fromAddress[fromAddress.index(after: lt)..<gt]).trimmingCharacters(in: .whitespaces)
        }
        return fromAddress.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    /// Gmail's snippet when it sent one, else the start of the body — one
    /// line of whitespace-collapsed text.
    var previewText: String {
        let source: Substring
        if let snippet, !snippet.isEmpty {
            source = Substring(snippet)
        } else {
            source = body.prefix(600)
        }
        return String(source.split(whereSeparator: \.isWhitespace).joined(separator: " ").prefix(200))
    }
}

@MainActor
enum EmailDates {
    private static let parsers: [DateFormatter] = [
        "EEE, d MMM yyyy HH:mm:ss Z",
        "d MMM yyyy HH:mm:ss Z",
        "EEE, d MMM yyyy HH:mm Z",
        "d MMM yyyy HH:mm Z",
        "EEE, d MMM yyyy HH:mm:ss zzz",
    ].map { format in
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.dateFormat = format
        return f
    }
    private static let time: DateFormatter = {
        let f = DateFormatter(); f.dateStyle = .none; f.timeStyle = .short; return f
    }()
    private static let weekday: DateFormatter = {
        let f = DateFormatter(); f.setLocalizedDateFormatFromTemplate("EEE"); return f
    }()
    private static let monthDay: DateFormatter = {
        let f = DateFormatter(); f.setLocalizedDateFormatFromTemplate("MMMd"); return f
    }()
    private static let numeric: DateFormatter = {
        let f = DateFormatter(); f.dateStyle = .short; f.timeStyle = .none; return f
    }()
    private static let full: DateFormatter = {
        let f = DateFormatter(); f.dateStyle = .medium; f.timeStyle = .short; return f
    }()

    /// RFC 2822 as Gmail passes it through, trailing "(UTC)" comment and all.
    static func parse(_ raw: String) -> Date? {
        var s = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        if let comment = s.range(of: " (") { s = String(s[..<comment.lowerBound]) }
        for parser in parsers {
            if let date = parser.date(from: s) { return date }
        }
        return nil
    }

    /// Mail-style: a time today, "Yesterday", a weekday this week, else a date.
    static func listLabel(_ date: Date) -> String {
        let cal = Calendar.current
        let now = Date()
        if cal.isDateInToday(date) { return time.string(from: date) }
        if cal.isDateInYesterday(date) { return "Yesterday" }
        if let days = cal.dateComponents([.day], from: date, to: now).day, (0..<7).contains(days) {
            return weekday.string(from: date)
        }
        if cal.isDate(date, equalTo: now, toGranularity: .year) { return monthDay.string(from: date) }
        return numeric.string(from: date)
    }

    static func fullLabel(_ date: Date) -> String {
        full.string(from: date)
    }

    /// Deterministic — `String.hashValue` is seeded per launch, and a sender
    /// should keep their avatar color.
    static func stableIndex(_ key: String, modulo: Int) -> Int {
        let hash = key.lowercased().unicodeScalars.reduce(UInt32(5381)) { ($0 &* 33) &+ $1.value }
        return Int(hash % UInt32(max(modulo, 1)))
    }
}
