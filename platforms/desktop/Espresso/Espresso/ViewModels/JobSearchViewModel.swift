import Foundation
import Observation

/// The Job search section: the person's searches, the open one's ranked jobs,
/// and the open job. Polls a live search's cheap status every few seconds and
/// reloads the jobs only when its fingerprint changes.
@Observable @MainActor
final class JobSearchViewModel {
    enum Filter: String, CaseIterable, Identifiable {
        case all = "All"
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

    private let service = JobSearchService.shared

    var selectedSearch: JobSearchSummary? { detail?.search ?? searches.first { $0.id == selectedSearchId } }
    var visibleLeads: [JobLeadSummary] {
        Self.filtered(detail?.leads ?? [], filter: filter, showIrrelevant: showIrrelevant)
    }

    // MARK: Loading

    func load() async {
        do {
            let list = try await service.list()
            try Task.checkCancellation()
            searches = list.searches
            usage = list.usage
            consent = list.consent
            available = list.available
            hasLoaded = true
            if let id = selectedSearchId, !searches.contains(where: { $0.id == id }) {
                selectedSearchId = nil; detail = nil; selectedLeadId = nil; lead = nil
            }
            if selectedSearchId == nil, let first = searches.first {
                await select(first.id)
            } else if let id = selectedSearchId, detail == nil {
                await loadDetail(id)
            }
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

    func create(_ body: JobSearchService.CreateBody) async throws {
        let created = try await service.create(body)
        selectedSearchId = created.id
        detail = nil
        selectedLeadId = nil
        lead = nil
        await load()
    }

    func setState(_ state: String) async {
        guard let searchId = selectedSearchId, let leadId = selectedLeadId else { return }
        await perform {
            self.lead = try await self.service.updateLead(searchId, leadId, state: state)
            await self.loadDetail(searchId)
        }
    }

    func saveNotes(_ notes: String) async {
        guard let searchId = selectedSearchId, let leadId = selectedLeadId else { return }
        await perform {
            self.lead = try await self.service.updateLead(searchId, leadId, notes: notes)
        }
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

    func cancel() async {
        guard let searchId = selectedSearchId else { return }
        await perform { self.apply(try await self.service.cancel(searchId)) }
    }

    func delete(_ searchId: String) async {
        await perform {
            try await self.service.delete(searchId)
            if self.selectedSearchId == searchId {
                self.selectedSearchId = nil; self.detail = nil; self.selectedLeadId = nil; self.lead = nil
            }
            await self.load()
        }
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

    nonisolated static func filtered(_ leads: [JobLeadSummary], filter: Filter, showIrrelevant: Bool) -> [JobLeadSummary] {
        leads.filter { lead in
            if lead.isIrrelevant && !showIrrelevant && filter != .dismissed { return false }
            switch filter {
            case .all: return lead.userState != "dismissed"
            case .postedPay: return lead.compStatus == "posted" && lead.userState != "dismissed"
            case .saved: return lead.userState == "saved"
            case .applied: return lead.userState == "applied"
            case .dismissed: return lead.userState == "dismissed"
            }
        }
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

    nonisolated private static func trim(_ value: Double) -> String {
        value == value.rounded() ? String(Int(value)) : String(format: "%.2g", value)
    }

    nonisolated private static func money(_ value: Double) -> String {
        let formatter = NumberFormatter()
        formatter.numberStyle = .decimal
        formatter.maximumFractionDigits = value < 1_000 ? 2 : 0
        return formatter.string(from: NSNumber(value: value)) ?? String(Int(value))
    }

    /// A `mailto:` for the drafted outreach, only when it has an address.
    nonisolated static func mailtoURL(_ outreach: JobOutreach?) -> URL? {
        guard let outreach, let to = outreach.toEmail, !to.isEmpty,
              to.range(of: #"^[^@\s<>,;]+@[^@\s<>,;]+\.[^@\s<>,;]+$"#, options: .regularExpression) != nil
        else { return nil }
        var parts = URLComponents()
        parts.scheme = "mailto"
        parts.path = to
        parts.queryItems = [
            URLQueryItem(name: "subject", value: outreach.subject ?? ""),
            URLQueryItem(name: "body", value: outreach.body ?? ""),
        ]
        return parts.url
    }

    /// Only plain http(s) links are opened.
    nonisolated static func webURL(_ value: String?) -> URL? {
        guard let value, let url = URL(string: value),
              let scheme = url.scheme?.lowercased(), scheme == "http" || scheme == "https",
              url.host() != nil else { return nil }
        return url
    }
}
