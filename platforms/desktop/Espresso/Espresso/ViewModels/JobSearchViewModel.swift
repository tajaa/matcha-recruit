import Foundation
import Observation

/// One job search as Tasks shows it (its ranked jobs and the open job), and
/// starting a new one. Polls a live search's cheap status every few seconds
/// and reloads the jobs only when its fingerprint changes.
@Observable @MainActor
final class JobSearchViewModel {
    enum Filter: String, CaseIterable, Identifiable {
        case all = "All"
        /// The ones with a drafted approach: where to start.
        case drafted = "Drafted"
        case postedPay = "Pay posted"
        case saved = "Saved"
        case applied = "Applied"
        case dismissed = "Dismissed"
        var id: String { rawValue }
    }

    var searches: [JobSearchSummary] = []
    var usage: MWRunQuota?
    var consent: JobSearchConsent?
    var available = true
    var hasLoaded = false

    var selectedSearchId: String?
    var detail: JobSearchDetail?
    var selectedLeadId: String?
    var lead: JobLeadDetail?
    var leadLoading = false

    var filter: Filter = .all
    var showIrrelevant = false
    var busy = false
    var errorMessage: String?
    /// A 403 that names a plan: the view raises the paywall for it.
    var planFeature: String?
    /// The search `create` just started, for Tasks to open.
    var createdSearchId: String?
    /// Draft email was refused because Gmail isn't connected yet.
    var emailNotConnected = false

    private let service = JobSearchService.shared

    var selectedSearch: JobSearchSummary? { detail?.search ?? searches.first { $0.id == selectedSearchId } }
    var visibleLeads: [JobLeadSummary] {
        Self.filtered(detail?.leads ?? [], filter: filter, showIrrelevant: showIrrelevant)
    }

    // MARK: Loading

    /// One search on its own, as Tasks shows it: no list.
    func open(_ searchId: String, leadId: String? = nil) async {
        if selectedSearchId != searchId { reset() }
        errorMessage = nil
        await select(searchId, leadId: leadId)
        hasLoaded = detail != nil
    }

    /// What starting a search needs (the allowance, consent, whether this
    /// server has a listings provider), without loading any search.
    func prepareNew() async {
        do {
            let list = try await service.list()
            try Task.checkCancellation()
            usage = list.usage
            consent = list.consent
            available = list.available
        } catch is CancellationError {
        } catch { report(error) }
    }

    func select(_ searchId: String, leadId: String? = nil) async {
        if selectedSearchId != searchId {
            selectedSearchId = searchId
            detail = nil
            selectedLeadId = nil
            lead = nil
        }
        await loadDetail(searchId)
        if let leadId { await selectLead(leadId) }
    }

    private func loadDetail(_ searchId: String) async {
        do {
            let loaded = try await service.detail(searchId)
            try Task.checkCancellation()
            guard selectedSearchId == searchId else { return }
            apply(loaded)
            if let leadId = selectedLeadId, !loaded.leads.contains(where: { $0.id == leadId }) {
                selectedLeadId = nil; lead = nil
            }
        } catch is CancellationError {
        } catch { report(error) }
    }

    private func apply(_ loaded: JobSearchDetail) {
        detail = loaded
        if let i = searches.firstIndex(where: { $0.id == loaded.search.id }) {
            searches[i] = loaded.search
        }
    }

    /// The poll: cheap status, full reload only on a change.
    func poll() async {
        guard let id = selectedSearchId, let current = detail else { return }
        let liveJobs = current.leads.contains { $0.isDrafting }
        guard current.search.isLive || liveJobs else { return }
        do {
            let status = try await service.status(id)
            try Task.checkCancellation()
            guard selectedSearchId == id else { return }
            if Self.changed(current, status) {
                await loadDetail(id)
                if let leadId = selectedLeadId { await refreshLead(leadId) }
                if !JobSearchStatus.isLive(status.status) { await refreshUsage() }
            }
        } catch is CancellationError {
        } catch { report(error) }
    }

    private func refreshUsage() async {
        if let list = try? await service.list() {
            usage = list.usage
            searches = list.searches
        }
    }

    func selectLead(_ leadId: String?) async {
        selectedLeadId = leadId
        guard let leadId else { lead = nil; return }
        if lead?.summary.id != leadId { lead = nil }
        await refreshLead(leadId)
    }

    private func refreshLead(_ leadId: String) async {
        guard let searchId = selectedSearchId else { return }
        leadLoading = true
        defer { leadLoading = false }
        do {
            let loaded = try await service.lead(searchId, leadId)
            try Task.checkCancellation()
            if selectedLeadId == leadId { lead = loaded }
        } catch is CancellationError {
        } catch { report(error) }
    }

    // MARK: Actions

    /// Start a search; Tasks opens it (`createdSearchId`).
    func create(_ body: JobSearchService.CreateBody) async throws {
        let created = try await service.create(body)
        createdSearchId = created.id
    }

    /// Saved / Applied / Dismissed for the job on screen. `leadId` is the job
    /// the person acted on, not whichever is selected when the save returns.
    func setState(_ state: String, leadId: String) async {
        guard let searchId = selectedSearchId else { return }
        await perform {
            let updated = try await self.service.updateLead(searchId, leadId, state: state)
            self.show(updated)
            await self.loadDetail(searchId)
        }
    }

    func saveNotes(_ notes: String, leadId: String) async {
        guard let searchId = selectedSearchId else { return }
        await perform { self.show(try await self.service.updateLead(searchId, leadId, notes: notes)) }
    }

    /// A save's answer replaces the open job only if that job is still open:
    /// clicking another job while it saved must not put the old one back.
    private func show(_ updated: JobLeadDetail) {
        if selectedLeadId == updated.summary.id { lead = updated }
    }

    func rerank(_ weights: JobSearchWeights) async {
        guard let searchId = selectedSearchId else { return }
        await perform { self.apply(try await self.service.rerank(searchId, weights: weights)) }
    }

    func redraft() async {
        guard let searchId = selectedSearchId, let leadId = selectedLeadId else { return }
        await perform {
            self.apply(try await self.service.redraft(searchId, leadId))
            await self.refreshLead(leadId)
        }
    }

    /// Put a job's first message in the person's Gmail drafts. Returns the
    /// draft's id (the same draft again while it is still in Gmail).
    func draftEmail(leadId: String) async -> String? {
        guard let searchId = selectedSearchId, !busy else { return nil }
        busy = true
        errorMessage = nil
        emailNotConnected = false
        defer { busy = false }
        do {
            let result = try await service.draftEmail(searchId, leadId)
            if let updated = result.lead {
                if selectedLeadId == leadId { lead = updated }
                if let i = detail?.leads.firstIndex(where: { $0.id == leadId }) {
                    detail?.leads[i] = updated.summary
                }
            }
            return result.draftId
        } catch {
            // Not connected is shown beside the button, with a way to Email.
            if (error as? APIError)?.detailCode == "email_not_connected" {
                emailNotConnected = true
            } else {
                report(error)
            }
            return nil
        }
    }

    func cancel() async {
        guard let searchId = selectedSearchId else { return }
        await perform { self.apply(try await self.service.cancel(searchId)) }
    }

    private func perform(_ action: @escaping () async throws -> Void) async {
        guard !busy else { return }
        busy = true
        errorMessage = nil
        defer { busy = false }
        do { try await action() } catch { report(error) }
    }

    func report(_ error: Error) {
        if let api = error as? APIError {
            if let plan = api.planRequirement { planFeature = plan.feature }
            errorMessage = AssistantText.message(for: api)
        } else {
            errorMessage = error.localizedDescription
        }
    }

    /// The person signed out, or another account signed in.
    func reset() {
        searches = []; usage = nil; consent = nil; hasLoaded = false
        selectedSearchId = nil; detail = nil; selectedLeadId = nil; lead = nil
        errorMessage = nil; planFeature = nil
    }

    // MARK: Pure helpers (tested)

    nonisolated static func changed(_ detail: JobSearchDetail, _ status: JobSearchStatusView) -> Bool {
        status.fingerprint != detail.fingerprint || status.status != detail.search.status
            || status.leadCount != detail.leads.count
    }

    /// Where a finished search stands, for its Next steps.
    struct Progress: Equatable {
        var drafted = 0
        var saved = 0
        var emailsWaiting = 0
        var emailsSent = 0
        var applied = 0

        var line: String? {
            let parts = [
                saved > 0 ? "\(saved) saved" : nil,
                emailsWaiting > 0 ? (emailsWaiting == 1 ? "1 email in drafts" : "\(emailsWaiting) emails in drafts") : nil,
                emailsSent > 0 ? "\(emailsSent) sent" : nil,
                applied > 0 ? "\(applied) applied" : nil,
            ].compactMap { $0 }
            return parts.isEmpty ? nil : parts.joined(separator: " \u{00B7} ")
        }
    }

    nonisolated static func progress(_ leads: [JobLeadSummary]) -> Progress {
        var out = Progress()
        for lead in leads where lead.userState != "dismissed" {
            if lead.hasApproach && !lead.isIrrelevant { out.drafted += 1 }
            if lead.userState == "saved" { out.saved += 1 }
            if lead.userState == "applied" { out.applied += 1 }
            if lead.emailWaiting { out.emailsWaiting += 1 }
            if lead.emailSentAt != nil { out.emailsSent += 1 }
        }
        return out
    }

    /// A posting's text as it reads best: each line trimmed (pages indent with
    /// spaces and non-breaking spaces), runs of spaces collapsed, and at most
    /// one blank line between paragraphs.
    nonisolated static func tidyPosting(_ text: String) -> String {
        let lines = text.replacingOccurrences(of: "\r\n", with: "\n")
            .replacingOccurrences(of: "\u{00A0}", with: " ")
            .components(separatedBy: "\n")
            .map { $0.split(separator: " ", omittingEmptySubsequences: true).joined(separator: " ")
                .trimmingCharacters(in: .whitespaces) }
        var out: [String] = []
        for line in lines {
            if line.isEmpty {
                if let last = out.last, !last.isEmpty { out.append("") }
            } else {
                out.append(line)
            }
        }
        while out.last == "" { out.removeLast() }
        return out.joined(separator: "\n")
    }

    nonisolated static func filtered(_ leads: [JobLeadSummary], filter: Filter, showIrrelevant: Bool) -> [JobLeadSummary] {
        leads.filter { lead in
            // Screened-out jobs hide from the browsing tabs, never from the
            // person's own lists: a job they saved or applied to stays there.
            if lead.isIrrelevant && !showIrrelevant && (filter == .all || filter == .postedPay || filter == .drafted) {
                return false
            }
            switch filter {
            case .all: return lead.userState != "dismissed"
            case .drafted: return lead.hasApproach && lead.userState != "dismissed"
            case .postedPay: return lead.compStatus == "posted" && lead.userState != "dismissed"
            case .saved: return lead.userState == "saved"
            case .applied: return lead.userState == "applied"
            case .dismissed: return lead.userState == "dismissed"
            }
        }
    }

    /// Whether a failed create means a retry is a new request. Only when the
    /// server answered that it didn't start one: a refusal (4xx), or a 503 for
    /// a search it couldn't queue (marked failed, which is free). With no
    /// answer, or any other error, the search may be running, so the retry
    /// keeps the request id and the server hands back that search.
    nonisolated static func retryIsNewRequest(_ error: Error) -> Bool {
        guard let api = error as? APIError, case let .httpError(code, _) = api else { return false }
        return (400..<500).contains(code) || code == 503
    }

    nonisolated static func dollars(_ value: Int) -> String {
        "$" + money(Double(value))
    }

    nonisolated static func usageLine(_ usage: MWRunQuota?) -> String? {
        guard let usage, usage.limit > 0 else { return nil }
        return "\(usage.remaining) of \(usage.limit) searches left this month"
    }

    /// "4/5" style fit, or an en dash when the job was not screened.
    nonisolated static func fitText(_ fit: Int?) -> String {
        fit.map { "\($0)/5" } ?? "\u{2013}"
    }

    nonisolated static func compBadge(_ status: String) -> String {
        switch status {
        case "posted": return "Posted"
        case "mentioned": return "Mentioned"
        default: return "Not posted"
        }
    }

    /// A pay part as one line: "$250,000–$300,000 a year", "30% target", "0.5–1% equity".
    nonisolated static func partLine(_ name: String, _ part: JobCompPart) -> String {
        if let lo = part.pctMin {
            let hi = part.pctMax ?? lo
            let range = lo == hi ? "\(trim(lo))%" : "\(trim(lo))–\(trim(hi))%"
            return name == "Bonus" ? "\(range) of base" : range
        }
        if let lo = part.min {
            let hi = part.max ?? lo
            let symbol = (part.currency ?? "USD") == "USD" ? "$" : "\(part.currency ?? "") "
            let amount = lo == hi ? "\(symbol)\(money(lo))" : "\(symbol)\(money(lo))–\(symbol)\(money(hi))"
            let period = part.period.map { $0 == "hour" ? " an hour" : " a \($0)" } ?? ""
            return amount + period
        }
        return part.status == "mentioned" ? "Mentioned, no figure" : "Not posted"
    }

    /// "30", "12.5", "1.25", "112.5": up to six significant digits and no
    /// exponent, matching the server's pay line (Python's `:g`).
    nonisolated static func trim(_ value: Double) -> String {
        value == value.rounded() && abs(value) < 1e15 ? String(Int(value)) : String(format: "%g", value)
    }

    nonisolated private static func money(_ value: Double) -> String {
        let formatter = NumberFormatter()
        formatter.numberStyle = .decimal
        formatter.maximumFractionDigits = value < 1_000 ? 2 : 0
        return formatter.string(from: NSNumber(value: value)) ?? String(Int(value))
    }

    /// Only plain http(s) links are opened.
    nonisolated static func webURL(_ value: String?) -> URL? {
        guard let value, let url = URL(string: value),
              let scheme = url.scheme?.lowercased(), scheme == "http" || scheme == "https",
              url.host() != nil else { return nil }
        return url
    }
}
