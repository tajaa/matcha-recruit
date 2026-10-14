import Foundation

// Espresso Job search (`/matcha-work/job-searches`). The server finds,
// screens, prices and ranks the jobs, and drafts how to approach the best
// ones; this side shows them and keeps the person's own status and notes.
// Every field the server may leave out decodes as nil or empty, so an older
// or newer server never breaks the screen.

private extension KeyedDecodingContainer {
    func value<T: Decodable>(_ key: Key) -> T? { (try? decodeIfPresent(T.self, forKey: key)) ?? nil }
    func list<T: Decodable>(_ key: Key) -> [T] { (try? decodeIfPresent([T].self, forKey: key)) ?? [] }
}

/// How much each part counts in the ranking (0...1 each; the server renormalizes).
struct JobSearchWeights: Codable, Hashable {
    var base: Double = 0.45
    var bonus: Double = 0.2
    var equity: Double = 0.2
    var fit: Double = 0.15

    static let standard = JobSearchWeights()
    var anyAboveZero: Bool { base + bonus + equity + fit > 0 }
}

struct JobSearchCriteria: Encodable, Hashable {
    var titles: [String] = []
    var locations: [String] = []
    /// `any`, `remote_only` or `onsite_only`.
    var remote: String = "any"
    var baseFloor: Int? = nil
    var currency: String = "USD"
    var excludeCompanies: [String] = []
    var dealBreakers: [String] = []

    enum CodingKeys: String, CodingKey {
        case titles, locations, remote, currency
        case baseFloor = "base_floor"
        case excludeCompanies = "exclude_companies"
        case dealBreakers = "deal_breakers"
    }

    /// "COO, Chief Operating Officer" -> ["COO", "Chief Operating Officer"].
    static func split(_ text: String) -> [String] {
        var seen = Set<String>()
        return text.split(whereSeparator: { $0 == "," || $0 == "\n" || $0 == ";" })
            .map { $0.trimmingCharacters(in: .whitespaces) }
            .filter { !$0.isEmpty && seen.insert($0.lowercased()).inserted }
    }
}

struct JobSearchProgress: Decodable, Hashable {
    var note: String?
    var found: Int?
    var relevant: Int?
    var postedPay: Int?

    enum CodingKeys: String, CodingKey {
        case note, found, relevant
        case postedPay = "posted_pay"
    }

    init(note: String? = nil, found: Int? = nil, relevant: Int? = nil, postedPay: Int? = nil) {
        self.note = note; self.found = found; self.relevant = relevant; self.postedPay = postedPay
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        note = c.value(.note)
        found = c.value(.found)
        relevant = c.value(.relevant)
        postedPay = c.value(.postedPay)
    }
}

/// The search's place in the pipeline, for the stepper.
enum JobSearchPhase: Int, CaseIterable, Identifiable {
    case planning, searching, screening, reading, drafting, done

    var id: Int { rawValue }

    var label: String {
        switch self {
        case .planning: return "Plan"
        case .searching: return "Search"
        case .screening: return "Screen"
        case .reading: return "Read pay"
        case .drafting: return "Draft approaches"
        case .done: return "Done"
        }
    }

    /// nil for a status that is not a step (failed / cancelled).
    static func from(status: String) -> JobSearchPhase? {
        switch status {
        case "queued", "planning": return .planning
        case "discovering": return .searching
        case "screening": return .screening
        case "enriching": return .reading
        case "approaching": return .drafting
        case "done": return .done
        default: return nil
        }
    }
}

enum JobSearchStatus {
    static let live: Set<String> = ["queued", "planning", "discovering", "screening", "enriching", "approaching"]

    static func isLive(_ status: String) -> Bool { live.contains(status) }

    static func label(_ status: String) -> String {
        switch status {
        case "queued": return "Queued"
        case "planning": return "Planning"
        case "discovering": return "Searching"
        case "screening": return "Screening"
        case "enriching": return "Reading postings"
        case "approaching": return "Drafting approaches"
        case "done": return "Done"
        case "failed": return "Didn't finish"
        case "cancelled": return "Cancelled"
        default: return status.capitalized
        }
    }
}

struct JobSearchSummary: Decodable, Identifiable, Hashable {
    let id: String
    var title: String
    var ask: String
    var status: String
    var progress: JobSearchProgress
    var error: String?
    var leadCount: Int
    var postedPayCount: Int
    var weights: JobSearchWeights
    var useResume: Bool
    var createdAt: String?

    enum CodingKeys: String, CodingKey {
        case id, title, ask, status, progress, error, weights
        case leadCount = "lead_count"
        case postedPayCount = "posted_pay_count"
        case useResume = "use_resume"
        case createdAt = "created_at"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(String.self, forKey: .id)
        title = c.value(.title) ?? ""
        ask = c.value(.ask) ?? ""
        status = c.value(.status) ?? "queued"
        progress = c.value(.progress) ?? JobSearchProgress()
        error = c.value(.error)
        leadCount = c.value(.leadCount) ?? 0
        postedPayCount = c.value(.postedPayCount) ?? 0
        weights = c.value(.weights) ?? .standard
        useResume = c.value(.useResume) ?? false
        createdAt = c.value(.createdAt)
    }

    var isLive: Bool { JobSearchStatus.isLive(status) }
    var displayTitle: String { title.isEmpty ? ask : title }
}

struct JobLeadSummary: Decodable, Identifiable, Hashable {
    let id: String
    var title: String
    var company: String
    var location: String
    var remote: Bool?
    var sourceUrl: String?
    var applyUrl: String?
    var postedText: String?
    var compLine: String
    /// `posted`, `mentioned` or `not_disclosed`.
    var compStatus: String
    var compAnnualMin: Double?
    var compAnnualMax: Double?
    var compCurrency: String?
    var bonusPct: Double?
    var equityPct: Double?
    var fitScore: Int?
    var screenStatus: String
    var rank: Int?
    var rankBand: Int?
    var flags: [String]
    /// `new`, `saved`, `applied` or `dismissed`.
    var userState: String
    /// `none`, `queued`, `drafting`, `done` or `failed`.
    var approachStatus: String

    enum CodingKeys: String, CodingKey {
        case id, title, company, location, remote, rank, flags
        case sourceUrl = "source_url"
        case applyUrl = "apply_url"
        case postedText = "posted_text"
        case compLine = "comp_line"
        case compStatus = "comp_status"
        case compAnnualMin = "comp_annual_min"
        case compAnnualMax = "comp_annual_max"
        case compCurrency = "comp_currency"
        case bonusPct = "bonus_pct"
        case equityPct = "equity_pct"
        case fitScore = "fit_score"
        case screenStatus = "screen_status"
        case rankBand = "rank_band"
        case userState = "user_state"
        case approachStatus = "approach_status"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(String.self, forKey: .id)
        title = c.value(.title) ?? ""
        company = c.value(.company) ?? ""
        location = c.value(.location) ?? ""
        remote = c.value(.remote)
        sourceUrl = c.value(.sourceUrl)
        applyUrl = c.value(.applyUrl)
        postedText = c.value(.postedText)
        compLine = c.value(.compLine) ?? "Pay not posted"
        compStatus = c.value(.compStatus) ?? "not_disclosed"
        compAnnualMin = c.value(.compAnnualMin)
        compAnnualMax = c.value(.compAnnualMax)
        compCurrency = c.value(.compCurrency)
        bonusPct = c.value(.bonusPct)
        equityPct = c.value(.equityPct)
        fitScore = c.value(.fitScore)
        screenStatus = c.value(.screenStatus) ?? "pending"
        rank = c.value(.rank)
        rankBand = c.value(.rankBand)
        flags = c.list(.flags)
        userState = c.value(.userState) ?? "new"
        approachStatus = c.value(.approachStatus) ?? "none"
    }

    var isIrrelevant: Bool { screenStatus == "irrelevant" }
    var isDrafting: Bool { approachStatus == "queued" || approachStatus == "drafting" }
}

struct JobSearchDetail: Decodable {
    var search: JobSearchSummary
    var leads: [JobLeadSummary]
    var fingerprint: String

    enum CodingKeys: String, CodingKey { case leads, fingerprint }

    init(from decoder: Decoder) throws {
        search = try JobSearchSummary(from: decoder)
        let c = try decoder.container(keyedBy: CodingKeys.self)
        leads = c.list(.leads)
        fingerprint = c.value(.fingerprint) ?? ""
    }
}

struct JobSearchStatusView: Decodable {
    var id: String
    var status: String
    var progress: JobSearchProgress
    var error: String?
    var leadCount: Int
    var fingerprint: String

    enum CodingKeys: String, CodingKey {
        case id, status, progress, error, fingerprint
        case leadCount = "lead_count"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(String.self, forKey: .id)
        status = c.value(.status) ?? "queued"
        progress = c.value(.progress) ?? JobSearchProgress()
        error = c.value(.error)
        leadCount = c.value(.leadCount) ?? 0
        fingerprint = c.value(.fingerprint) ?? ""
    }
}

struct JobEvidence: Decodable, Hashable {
    var quote: String?
    var origin: String?
    var url: String?

    var originLabel: String {
        switch origin {
        case "ats_api": return "From the job board's data"
        case "jsonld": return "From the posting page's data"
        case "google_jobs": return "From Google Jobs"
        case "page": return "From the posting page"
        default: return "From the posting"
        }
    }
}

struct JobCompPart: Decodable, Hashable {
    var status: String?
    var kind: String?
    var min: Double?
    var max: Double?
    var currency: String?
    var period: String?
    var annualMin: Double?
    var annualMax: Double?
    var pctMin: Double?
    var pctMax: Double?
    var evidence: JobEvidence?

    enum CodingKeys: String, CodingKey {
        case status, kind, min, max, currency, period, evidence
        case annualMin = "annual_min"
        case annualMax = "annual_max"
        case pctMin = "pct_min"
        case pctMax = "pct_max"
    }
}

struct JobComp: Decodable, Hashable {
    var base: JobCompPart?
    var bonus: JobCompPart?
    var equity: JobCompPart?

    var parts: [(String, JobCompPart)] {
        [("Base", base), ("Bonus", bonus), ("Equity", equity)].compactMap { name, part in part.map { (name, $0) } }
    }
}

struct JobQuestion: Decodable, Hashable {
    var key: String?
    var label: String?
    var required: Bool?
    var type: String?
    var options: [String]?
    var kind: String?
    var question: String?
    var questionKey: String?

    enum CodingKeys: String, CodingKey {
        case key, label, required, type, options, kind, question
        case questionKey = "question_key"
    }

    var text: String { label ?? question ?? key ?? "" }
}

struct JobContact: Decodable, Hashable {
    var name: String
    var role: String?
    var sourceUrl: String?

    enum CodingKeys: String, CodingKey {
        case name, role
        case sourceUrl = "source_url"
    }
}

struct JobOutreach: Decodable, Hashable {
    var toEmail: String?
    var subject: String?
    var body: String?

    enum CodingKeys: String, CodingKey {
        case subject, body
        case toEmail = "to_email"
    }
}

struct JobAnswer: Decodable, Hashable {
    var questionKey: String?
    var question: String
    var answer: String
    var likely: Bool?

    enum CodingKeys: String, CodingKey {
        case question, answer, likely
        case questionKey = "question_key"
    }
}

struct JobApproach: Decodable, Hashable {
    var summary: String?
    var channel: String?
    var steps: [String]
    var talkingPoints: [String]
    var negotiation: [String]
    var contacts: [JobContact]
    var outreach: JobOutreach?
    var answers: [JobAnswer]
    var unanswered: [JobQuestion]
    var coverLetter: String?
    var sources: [String]

    enum CodingKeys: String, CodingKey {
        case summary, channel, steps, negotiation, contacts, outreach, answers, unanswered, sources
        case talkingPoints = "talking_points"
        case coverLetter = "cover_letter"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        summary = c.value(.summary)
        channel = c.value(.channel)
        steps = c.list(.steps)
        talkingPoints = c.list(.talkingPoints)
        negotiation = c.list(.negotiation)
        contacts = c.list(.contacts)
        outreach = c.value(.outreach)
        answers = c.list(.answers)
        unanswered = c.list(.unanswered)
        coverLetter = c.value(.coverLetter)
        sources = c.list(.sources)
    }

    var isEmpty: Bool { (summary ?? "").isEmpty && steps.isEmpty && answers.isEmpty && (coverLetter ?? "").isEmpty }

    var channelLabel: String {
        switch channel {
        case "referral": return "Referral"
        case "hiring_manager": return "Hiring manager"
        case "recruiter": return "Recruiter"
        case "search_firm": return "Search firm"
        default: return "Application portal"
        }
    }
}

struct JobLeadAts: Decodable, Hashable {
    var provider: String?
    var questions: [JobQuestion]

    enum CodingKeys: String, CodingKey { case provider, questions }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        provider = c.value(.provider)
        questions = c.list(.questions)
    }
}

struct JobLeadDetail: Decodable {
    var summary: JobLeadSummary
    var description: String
    var comp: JobComp
    var ats: JobLeadAts?
    var payLawHint: String?
    var screenReason: String?
    var fitReasons: [String]
    var approach: JobApproach?
    var notes: String

    enum CodingKeys: String, CodingKey {
        case description, comp, ats, approach, notes
        case payLawHint = "pay_law_hint"
        case screenReason = "screen_reason"
        case fitReasons = "fit_reasons"
    }

    init(from decoder: Decoder) throws {
        summary = try JobLeadSummary(from: decoder)
        let c = try decoder.container(keyedBy: CodingKeys.self)
        description = c.value(.description) ?? ""
        comp = c.value(.comp) ?? JobComp()
        ats = c.value(.ats)
        payLawHint = c.value(.payLawHint)
        screenReason = c.value(.screenReason)
        fitReasons = c.list(.fitReasons)
        let approach: JobApproach? = c.value(.approach)
        self.approach = (approach?.isEmpty ?? true) ? nil : approach
        notes = c.value(.notes) ?? ""
    }
}

struct JobSearchConsent: Decodable {
    var granted: Bool
    var disclosure: AssistantDisclosure?
}

struct JobSearchList: Decodable {
    var searches: [JobSearchSummary]
    var usage: MWRunQuota?
    var consent: JobSearchConsent?
    var available: Bool

    enum CodingKeys: String, CodingKey { case searches, usage, consent, available }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        searches = c.list(.searches)
        usage = c.value(.usage)
        consent = c.value(.consent)
        available = c.value(.available) ?? true
    }
}

/// The person's saved résumé (`/users/me/resume`), as much as this screen shows.
struct ProfileResume: Decodable {
    var filename: String
    var updatedAt: String?
    var currentTitle: String?

    enum CodingKeys: String, CodingKey {
        case filename
        case updatedAt = "updated_at"
        case parsedData = "parsed_data"
    }

    private enum ParsedKeys: String, CodingKey {
        case currentTitle = "current_title"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        filename = c.value(.filename) ?? "Résumé"
        updatedAt = c.value(.updatedAt)
        let parsed = try? c.nestedContainer(keyedBy: ParsedKeys.self, forKey: .parsedData)
        currentTitle = parsed.flatMap { (try? $0.decodeIfPresent(String.self, forKey: .currentTitle)) ?? nil }
    }
}

/// A hand-off from a job to a new Espresso conversation, like Sales'.
struct AssistantJobContext: Identifiable {
    let id = UUID()
    let owner: String
    let searchId: String
    let jobId: String
    let title: String

    var conversationTitle: String { String("Job: \(title)".prefix(100)) }

    var prompt: String {
        "Help me with the job \(jobId) in my job search \(searchId). Read the job first: the posting, its pay "
        + "evidence and the drafted approach. Then help me tighten the outreach, the application answers and "
        + "the cover letter. Don't send or apply for anything.\n\nMy instructions: "
    }
}

/// A search (and optionally one of its jobs) for the Job search section to open.
struct JobSearchFocus: Equatable {
    let searchId: String
    let leadId: String?
}
