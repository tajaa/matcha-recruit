import Foundation

// Espresso Tasks (`/matcha-work/agent-tasks`). The server runs each task in
// the background (finding, reading, screening and ranking what fits) and
// keeps every fact with the quote and page it came from; this side shows the
// tasks and their findings and sends follow-ups. Every field the server may
// leave out decodes as nil or empty, so an older or newer server never breaks
// the screen.

private extension KeyedDecodingContainer {
    func value<T: Decodable>(_ key: Key) -> T? { (try? decodeIfPresent(T.self, forKey: key)) ?? nil }
    func list<T: Decodable>(_ key: Key) -> [T] { (try? decodeIfPresent([T].self, forKey: key)) ?? [] }
}

struct AgentTaskProgress: Decodable, Hashable {
    var note: String?
    var found: Int?
    var shown: Int?
}

/// Where one fact came from: the words on the page and the page.
struct AgentTaskEvidence: Decodable, Hashable {
    var quote: String?
    var url: String?
    /// `provider`, `jsonld`, `leasing`, `page_text`, `browser` or `model`.
    var origin: String?

    var originLabel: String {
        switch origin {
        case "provider": return "From the listings provider"
        case "leasing": return "From the building's leasing system"
        case "jsonld": return "From the page's structured data"
        case "page_text", "browser": return "From the page's text"
        case "model": return "Quoted by Espresso"
        default: return ""
        }
    }
}

/// One fact about a finding, as the server shows it.
struct AgentTaskField: Decodable, Hashable {
    var display: String
    /// `verified` (read on the finding's own page) or `claimed` (quoted from
    /// some other page). A claimed fact never rules a finding in or out.
    var status: String
    var number: Double?
    var evidence: AgentTaskEvidence?

    var isVerified: Bool { status == "verified" }

    enum CodingKeys: String, CodingKey { case display, status, value, evidence }

    init(display: String, status: String = "verified", number: Double? = nil, evidence: AgentTaskEvidence? = nil) {
        self.display = display; self.status = status; self.number = number; self.evidence = evidence
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        display = c.value(.display) ?? ""
        status = c.value(.status) ?? "claimed"
        number = c.value(.value)
        evidence = c.value(.evidence)
    }
}

struct AgentTaskImage: Decodable, Hashable {
    var url: String
    var pageUrl: String?
    var alt: String?

    enum CodingKeys: String, CodingKey {
        case url, alt
        case pageUrl = "page_url"
    }
}

/// One home to let in an apartment building, as its leasing system lists it
/// (SightMap's unit map, Avalon's site): every figure is the building's own.
struct AgentTaskUnit: Decodable, Hashable, Identifiable {
    var id: String
    var number: String?
    var floor: String?
    var plan: String?
    var beds: Double?
    var baths: Double?
    var sqft: Double?
    var rent: Double
    /// A month's rent over the lease after a special that frees stated time.
    var netRent: Double?
    var netNote: String?
    /// ISO date it can be moved into.
    var available: String?
    var leaseMonths: Int?
    var special: String?
    /// The floor plan, on our CDN (nil when it couldn't be copied there).
    var planImage: String?
    var tourUrl: String?
    var url: String?
    /// Meets every one of the person's limits at once; nil before ranking.
    var fits: Bool?

    enum CodingKeys: String, CodingKey {
        case id, number, floor, plan, beds, baths, sqft, rent, available, special, url, fits
        case netRent = "net_rent", netNote = "net_note", leaseMonths = "lease_months"
        case planImage = "plan_image", tourUrl = "tour_url"
    }

    init(id: String, number: String? = nil, floor: String? = nil, beds: Double? = nil, baths: Double? = nil,
         sqft: Double? = nil, rent: Double, netRent: Double? = nil, netNote: String? = nil, available: String? = nil,
         leaseMonths: Int? = nil, special: String? = nil, fits: Bool? = nil) {
        self.id = id; self.number = number; self.floor = floor; self.plan = nil; self.beds = beds; self.baths = baths
        self.sqft = sqft; self.rent = rent; self.netRent = netRent; self.netNote = netNote; self.available = available
        self.leaseMonths = leaseMonths; self.special = special; self.planImage = nil; self.tourUrl = nil
        self.url = nil; self.fits = fits
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        number = c.value(.number)
        id = c.value(.id) ?? number ?? ""
        floor = c.value(.floor)
        plan = c.value(.plan)
        beds = c.value(.beds)
        baths = c.value(.baths)
        sqft = c.value(.sqft)
        rent = c.value(.rent) ?? 0
        netRent = c.value(.netRent)
        netNote = c.value(.netNote)
        available = c.value(.available)
        leaseMonths = c.value(.leaseMonths)
        special = c.value(.special)
        planImage = c.value(.planImage)
        tourUrl = c.value(.tourUrl)
        url = c.value(.url)
        fits = c.value(.fits)
    }

    /// "#B201 · Floor 2 · 2 bd · 1 ba · 910 sq ft"
    var layoutLine: String {
        var parts = [number.map { "#\($0)" } ?? "A home"]
        if let floor, !floor.isEmpty { parts.append("Floor \(floor)") }
        if let beds { parts.append(beds == 0 ? "Studio" : "\(AgentTaskUnit.figure(beds)) bd") }
        if let baths { parts.append("\(AgentTaskUnit.figure(baths)) ba") }
        if let sqft, sqft > 0 { parts.append("\(AgentTaskUnit.dollars(sqft).dropFirst()) sq ft") }
        return parts.joined(separator: " · ")
    }

    /// When it can be moved into: "Now" once the day has come (where the
    /// person is), else "Nov 4" ("Jan 25, 2027" in another year).
    func availableLabel(today: Date = Date(), zone: TimeZone = .current) -> String? {
        guard let available, let day = AgentTaskUnit.isoDay.date(from: String(available.prefix(10))) else { return nil }
        let local = DateFormatter()
        local.locale = Locale(identifier: "en_US_POSIX")
        local.timeZone = zone
        local.dateFormat = "yyyy-MM-dd"
        let now = local.string(from: today)
        let iso = AgentTaskUnit.isoDay.string(from: day)
        if iso <= now { return "Now" }
        let shown = DateFormatter()
        shown.locale = Locale(identifier: "en_US_POSIX")
        shown.timeZone = TimeZone(identifier: "UTC")
        shown.dateFormat = iso.prefix(4) == now.prefix(4) ? "MMM d" : "MMM d, yyyy"
        return shown.string(from: day)
    }

    static func dollars(_ value: Double) -> String {
        let format = NumberFormatter()
        format.numberStyle = .decimal
        format.maximumFractionDigits = 0
        format.locale = Locale(identifier: "en_US")
        return "$" + (format.string(from: NSNumber(value: value.rounded())) ?? String(Int(value)))
    }

    static func figure(_ value: Double) -> String {
        value == value.rounded() ? String(Int(value)) : String(value)
    }

    private static let isoDay: DateFormatter = {
        let format = DateFormatter()
        format.locale = Locale(identifier: "en_US_POSIX")
        format.timeZone = TimeZone(identifier: "UTC")
        format.dateFormat = "yyyy-MM-dd"
        return format
    }()
}

/// A building's homes in brief: how many are listed, how many fit, and the
/// cheapest that does (net of a stated special).
struct AgentTaskHomes: Decodable, Hashable {
    var count: Int
    /// nil before ranking.
    var fit: Int?
    var from: Double?

    /// "3 of 18 homes fit · from $2,949/mo", or "18 homes listed".
    var line: String {
        let homes = count == 1 ? "home" : "homes"
        guard let fit else { return "\(count) \(homes) listed" + (from.map { " · from \(AgentTaskUnit.dollars($0))/mo" } ?? "") }
        if fit == 0 { return "None of \(count) \(homes) fit" }
        return "\(fit) of \(count) \(homes) fit" + (from.map { " · from \(AgentTaskUnit.dollars($0))/mo" } ?? "")
    }
}

struct AgentTaskViolation: Decodable, Hashable {
    var field: String?
    var rule: String?
    var value: String?
}

/// A finding.
struct AgentTaskItem: Decodable, Identifiable, Hashable {
    var id: String
    var kind: String
    var title: String
    var subtitle: String
    var url: String?
    var origin: String?
    var provider: String?
    var fields: [String: AgentTaskField]
    var images: [AgentTaskImage]
    /// Its page as the browser drew it: never one of its photos.
    var screenshots: [AgentTaskImage]
    var status: String
    var fitScore: Int?
    var rank: Int?
    var rankBand: Int?
    var flags: [String]
    /// `new`, `saved`, `chosen` or `dismissed`.
    var userState: String
    // Detail only.
    var violations: [AgentTaskViolation]
    var fitReasons: [String]
    var notes: String
    /// What it can do in the world (buy it, book it), as its playbook says.
    var actions: [AgentTaskAction]
    /// What was done with it, newest first.
    var actionHistory: [AgentTaskActionRun]
    /// An apartment building's homes in brief (list), and one by one (detail).
    var homes: AgentTaskHomes?
    var units: [AgentTaskUnit]

    enum CodingKeys: String, CodingKey {
        case id, kind, title, subtitle, url, origin, provider, fields, images, screenshots, status, rank, flags
        case violations, notes, actions, homes, units
        case fitScore = "fit_score"
        case rankBand = "rank_band"
        case userState = "user_state"
        case fitReasons = "fit_reasons"
        case actionHistory = "action_history"
    }

    init(id: String, title: String, subtitle: String = "", url: String? = nil, fields: [String: AgentTaskField] = [:],
         rank: Int? = nil, rankBand: Int? = 0, flags: [String] = [], userState: String = "new", status: String = "verified") {
        self.id = id; self.kind = "other"; self.title = title; self.subtitle = subtitle; self.url = url
        self.origin = nil; self.provider = nil; self.fields = fields; self.images = []; self.screenshots = []
        self.status = status
        self.fitScore = nil; self.rank = rank; self.rankBand = rankBand; self.flags = flags; self.userState = userState
        self.violations = []; self.fitReasons = []; self.notes = ""
        self.actions = []; self.actionHistory = []
        self.homes = nil; self.units = []
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(String.self, forKey: .id)
        kind = c.value(.kind) ?? "other"
        title = c.value(.title) ?? ""
        subtitle = c.value(.subtitle) ?? ""
        url = c.value(.url)
        origin = c.value(.origin)
        provider = c.value(.provider)
        fields = c.value(.fields) ?? [:]
        images = c.list(.images)
        screenshots = c.list(.screenshots)
        status = c.value(.status) ?? "candidate"
        fitScore = c.value(.fitScore)
        rank = c.value(.rank)
        rankBand = c.value(.rankBand)
        flags = c.list(.flags)
        userState = c.value(.userState) ?? "new"
        violations = c.list(.violations)
        fitReasons = c.list(.fitReasons)
        notes = c.value(.notes) ?? ""
        actions = c.list(.actions)
        actionHistory = c.list(.actionHistory)
        homes = c.value(.homes)
        units = c.list(.units)
    }

    /// Hidden from the list unless asked: it breaks a limit, didn't fit,
    /// is gone, or the person dismissed it.
    var isHidden: Bool { (rankBand ?? 0) >= 9 }
    /// Something it was asked for can't be confirmed from its own page.
    var unconfirmed: [String] {
        flags.compactMap { $0.hasPrefix("unconfirmed:") ? String($0.dropFirst("unconfirmed:".count)) : nil }
    }
    var hiddenReason: String? {
        if userState == "dismissed" { return "Dismissed" }
        if flags.contains("unavailable") { return "No longer available" }
        if let rule = violations.first?.rule { return "Breaks a limit: \(rule)" }
        if flags.contains("irrelevant") { return "Not a fit" }
        return nil
    }
}

struct AgentTaskColumn: Decodable, Hashable, Identifiable {
    var key: String
    var label: String
    var type: String
    var id: String { key }
}

struct AgentTaskConstraint: Decodable, Hashable {
    var field: String?
    var op: String?
    var label: String
}

struct AgentTaskPlan: Decodable, Hashable {
    var summary: String
    var itemKind: String?
    var location: String?
    var columns: [AgentTaskColumn]
    var constraints: [AgentTaskConstraint]

    enum CodingKeys: String, CodingKey {
        case summary, location, columns, constraints
        case itemKind = "item_kind"
    }

    init(summary: String = "", columns: [AgentTaskColumn] = [], constraints: [AgentTaskConstraint] = []) {
        self.summary = summary; self.itemKind = nil; self.location = nil
        self.columns = columns; self.constraints = constraints
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        summary = c.value(.summary) ?? ""
        itemKind = c.value(.itemKind)
        location = c.value(.location)
        columns = c.list(.columns)
        constraints = c.list(.constraints)
    }
}

struct AgentTaskSection: Decodable, Hashable {
    var heading: String
    var bodyMd: String

    enum CodingKeys: String, CodingKey {
        case heading
        case bodyMd = "body_md"
    }
}

struct AgentTaskPick: Decodable, Hashable {
    var itemId: String
    var why: String

    enum CodingKeys: String, CodingKey {
        case why
        case itemId = "item_id"
    }
}

struct AgentTaskCounts: Decodable, Hashable {
    var found: Int?
    var shown: Int?
    var hidden: Int?
}

/// What one round found, in words.
struct AgentTaskRoundSummary: Decodable, Hashable {
    var headline: String?
    var summary: String?
    var sections: [AgentTaskSection]
    var top: [AgentTaskPick]
    var counts: AgentTaskCounts?

    enum CodingKeys: String, CodingKey { case headline, summary, sections, top, counts }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        headline = c.value(.headline)
        summary = c.value(.summary)
        sections = c.list(.sections)
        top = c.list(.top)
        counts = c.value(.counts)
    }
}

struct AgentTaskDocument: Decodable, Hashable {
    var journalId: String?
    var title: String?
    var items: Int?

    enum CodingKeys: String, CodingKey {
        case title, items
        case journalId = "journal_id"
    }
}

/// One piece of work on a task: the first run, a refine, "search more", a document.
struct AgentTaskRound: Decodable, Identifiable, Hashable {
    var id: String
    var n: Int
    /// `initial`, `refine`, `more`, `document`.
    var kind: String
    var directive: String
    var status: String
    var units: Int
    var itemsAdded: Int
    var summary: AgentTaskRoundSummary?
    var document: AgentTaskDocument?
    var error: String?

    enum CodingKeys: String, CodingKey {
        case id, n, kind, directive, status, units, summary, document, error
        case itemsAdded = "items_added"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(String.self, forKey: .id)
        n = c.value(.n) ?? 0
        kind = c.value(.kind) ?? "initial"
        directive = c.value(.directive) ?? ""
        status = c.value(.status) ?? "done"
        units = c.value(.units) ?? 0
        itemsAdded = c.value(.itemsAdded) ?? 0
        summary = c.value(.summary)
        document = c.value(.document)
        error = c.value(.error)
    }

    var label: String {
        switch kind {
        case "initial": return "First search"
        case "refine": return "Refined"
        case "more": return "Searched for more"
        case "document": return "Document"
        default: return kind.capitalized
        }
    }
}

/// A task, as the list and the detail both show it.
struct AgentTask: Decodable, Identifiable, Hashable {
    var id: String
    var playbook: String
    /// What kind of task it is, in the person's words ("Apartments", "Products").
    var playbookLabel: String = ""
    /// `chain` (Espresso's own), `job_search` (a job search, shown with its own view).
    var engine: String = "chain"
    var jobSearchId: String?
    var title: String
    var directive: String
    /// `queued`, `running`, `waiting`, `done`, `failed`, `cancelled`.
    var status: String
    var phase: String?
    var progress: AgentTaskProgress
    var error: String?
    var currentRound: Int
    var itemCount: Int
    var shownCount: Int
    var unseen: Bool
    var createdAt: Date?
    var completedAt: Date?

    enum CodingKeys: String, CodingKey {
        case id, playbook, engine, title, directive, status, phase, progress, error, unseen
        case jobSearchId = "job_search_id"
        case playbookLabel = "playbook_label"
        case currentRound = "current_round"
        case itemCount = "item_count"
        case shownCount = "shown_count"
        case createdAt = "created_at"
        case completedAt = "completed_at"
    }

    init(id: String, title: String, status: String, note: String? = nil, unseen: Bool = false) {
        self.id = id; self.playbook = "research"; self.title = title; self.directive = title
        self.status = status; self.phase = nil; self.progress = AgentTaskProgress(note: note)
        self.error = nil; self.currentRound = 1; self.itemCount = 0; self.shownCount = 0
        self.unseen = unseen; self.createdAt = nil; self.completedAt = nil
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(String.self, forKey: .id)
        playbook = c.value(.playbook) ?? "research"
        playbookLabel = c.value(.playbookLabel) ?? ""
        engine = c.value(.engine) ?? "chain"
        jobSearchId = c.value(.jobSearchId)
        title = c.value(.title) ?? ""
        directive = c.value(.directive) ?? ""
        status = c.value(.status) ?? "queued"
        phase = c.value(.phase)
        progress = c.value(.progress) ?? AgentTaskProgress()
        error = c.value(.error)
        currentRound = c.value(.currentRound) ?? 1
        itemCount = c.value(.itemCount) ?? 0
        shownCount = c.value(.shownCount) ?? 0
        unseen = c.value(.unseen) ?? false
        createdAt = (c.value(.createdAt) as String?).flatMap { parseMWDate($0) }
        completedAt = (c.value(.completedAt) as String?).flatMap { parseMWDate($0) }
    }

    var isLive: Bool { status == "queued" || status == "running" }
    var isWaiting: Bool { status == "waiting" }
    /// A job search: Tasks shows the search's own view for it.
    var isJobSearch: Bool { engine == "job_search" && jobSearchId != nil }
    var displayTitle: String { title.isEmpty ? directive : title }

    var statusLabel: String {
        switch status {
        case "queued": return "Starting…"
        case "running": return phaseLabel
        case "waiting": return "Needs you"
        case "done": return "Done"
        case "failed": return "Stopped"
        case "cancelled": return "Cancelled"
        default: return status.capitalized
        }
    }

    var phaseLabel: String {
        switch phase {
        case "plan": return "Planning…"
        case "providers", "discover": return "Searching…"
        case "enrich": return "Reading pages…"
        case "screen": return "Checking what fits…"
        case "rank": return "Ranking…"
        case "summarize": return "Writing it up…"
        case "refine": return "Reading your change…"
        // A job search's own phases.
        case "planning": return "Planning…"
        case "discovering": return "Searching…"
        case "screening": return "Checking what fits…"
        case "enriching": return "Reading postings…"
        case "approaching": return "Drafting approaches…"
        default: return "Working…"
        }
    }
}

/// `GET /agent-tasks/{id}`: the task, what it is looking for, its rounds and findings.
struct AgentTaskDetail: Decodable {
    var task: AgentTask
    var fingerprint: String
    var plan: AgentTaskPlan
    var rounds: [AgentTaskRound]
    var items: [AgentTaskItem]

    enum CodingKeys: String, CodingKey { case fingerprint, plan, rounds, items }

    init(task: AgentTask, plan: AgentTaskPlan = AgentTaskPlan(), rounds: [AgentTaskRound] = [], items: [AgentTaskItem] = []) {
        self.task = task; self.fingerprint = ""; self.plan = plan; self.rounds = rounds; self.items = items
    }

    init(from decoder: Decoder) throws {
        task = try AgentTask(from: decoder)
        let c = try decoder.container(keyedBy: CodingKeys.self)
        fingerprint = c.value(.fingerprint) ?? ""
        plan = c.value(.plan) ?? AgentTaskPlan()
        rounds = c.list(.rounds)
        items = c.list(.items)
    }

    var latestSummary: AgentTaskRoundSummary? {
        rounds.last(where: { $0.kind != "document" && $0.summary?.headline != nil })?.summary
    }
    var visibleItems: [AgentTaskItem] { items.filter { !$0.isHidden } }
    var hiddenItems: [AgentTaskItem] { items.filter(\.isHidden) }
    var canFollowUp: Bool { !task.isJobSearch && (task.status == "done" || task.status == "waiting") }
}

struct AgentTaskStatus: Decodable {
    var id: String
    var status: String
    var fingerprint: String

    enum CodingKeys: String, CodingKey { case id, status, fingerprint }
}

struct AgentTaskUnits: Decodable, Hashable {
    var limit: Int
    var used: Int
    var remaining: Int
}

struct AgentTaskList: Decodable {
    var tasks: [AgentTask]
    var usage: AgentTaskUnits?

    enum CodingKeys: String, CodingKey { case tasks, usage }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        tasks = c.list(.tasks)
        usage = c.value(.usage)
    }
}

/// The sidebar row's counts.
struct AgentTasksSummary: Decodable, Hashable {
    var running: Int = 0
    var waiting: Int = 0
    var unseen: Int = 0
}

/// The list's groups, in the order they show.
enum AgentTaskGroup: String, CaseIterable, Identifiable {
    case needsYou = "Needs you"
    case running = "Running"
    case done = "Done"

    var id: String { rawValue }

    static func of(_ task: AgentTask) -> AgentTaskGroup {
        if task.isWaiting { return .needsYou }
        if task.isLive { return .running }
        return .done
    }

    /// Non-empty groups with their tasks, newest first within each.
    static func grouped(_ tasks: [AgentTask]) -> [(AgentTaskGroup, [AgentTask])] {
        allCases.compactMap { group in
            let members = tasks.filter { of($0) == group }
                .sorted { ($0.createdAt ?? .distantPast) > ($1.createdAt ?? .distantPast) }
            return members.isEmpty ? nil : (group, members)
        }
    }
}

// MARK: - Requests

struct AgentTaskRoundRequest: Encodable {
    let requestId: String
    /// `refine`, `more` or `document`.
    let kind: String
    let directive: String
    let itemIds: [String]

    enum CodingKeys: String, CodingKey {
        case kind, directive
        case requestId = "request_id"
        case itemIds = "item_ids"
    }
}

/// An action's own fields (quantity, a date...), as typed.
struct AgentTaskActionRequest: Encodable {
    let params: [String: String]
}

struct AgentTaskItemPatch: Encodable {
    var userState: String?
    var notes: String?

    enum CodingKeys: String, CodingKey {
        case notes
        case userState = "user_state"
    }

    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encodeIfPresent(userState, forKey: .userState)
        try c.encodeIfPresent(notes, forKey: .notes)
    }
}

// MARK: - In chat

/// A task's card in the conversation it came from (`metadata.kind == "agent_task"`).
struct AgentTaskCard: Codable, Hashable {
    struct Item: Codable, Hashable, Identifiable {
        var id: String
        var title: String
        var subtitle: String
        var url: String?
        var fields: [String: String]
        var image: String?

        enum CodingKeys: String, CodingKey { case id, title, subtitle, url, fields, image }

        init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            id = try c.decode(String.self, forKey: .id)
            title = c.value(.title) ?? ""
            subtitle = c.value(.subtitle) ?? ""
            url = c.value(.url)
            fields = c.value(.fields) ?? [:]
            image = c.value(.image)
        }
    }

    /// `started`, or `update` (finished, stopped, needs the person).
    var event: String
    var taskId: String
    var title: String
    var status: String
    var note: String
    var headline: String?
    var items: [Item]

    enum CodingKeys: String, CodingKey {
        case event, title, status, note, headline, items
        case taskId = "task_id"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        event = c.value(.event) ?? "update"
        taskId = try c.decode(String.self, forKey: .taskId)
        title = c.value(.title) ?? ""
        status = c.value(.status) ?? "queued"
        note = c.value(.note) ?? ""
        headline = c.value(.headline)
        items = c.list(.items)
    }
}

/// A field on a form Espresso asked in chat (`prompt_kind == "ask_form"`).
/// Something a finding can do (buy it, book it), as the server declares it:
/// the app draws whatever it is sent, so a new action needs no app change.
struct AgentTaskAction: Decodable, Hashable, Identifiable {
    var key: String
    var label: String
    /// cart, calendar, envelope, link, phone.
    var icon: String
    var description: String
    var confirmLabel: String
    var params: [IntakeFormField]
    var available: Bool
    /// Why it can't be done for this finding.
    var reason: String?

    var id: String { key }

    enum CodingKeys: String, CodingKey {
        case key, label, icon, description, params, available, reason
        case confirmLabel = "confirm_label"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        key = try c.decode(String.self, forKey: .key)
        label = c.value(.label) ?? key
        icon = c.value(.icon) ?? "link"
        description = c.value(.description) ?? ""
        confirmLabel = c.value(.confirmLabel) ?? "Go ahead"
        params = c.list(.params)
        available = c.value(.available) ?? false
        reason = c.value(.reason)
    }

    var systemImage: String { AgentTaskAction.systemImage(icon) }

    static func systemImage(_ icon: String) -> String {
        switch icon {
        case "cart": return "cart"
        case "calendar": return "calendar.badge.plus"
        case "envelope": return "envelope"
        case "phone": return "phone"
        default: return "arrow.up.right.square"
        }
    }
}

struct AgentTaskActionLine: Decodable, Hashable {
    var label: String
    var value: String
}

/// What an action would do (before), or what came of it (after).
struct AgentTaskActionPreview: Decodable, Hashable {
    var title: String
    var lines: [AgentTaskActionLine]
    var note: String

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        title = c.value(.title) ?? ""
        lines = c.list(.lines)
        note = c.value(.note) ?? ""
    }

    enum CodingKeys: String, CodingKey { case title, lines, note }
}

struct AgentTaskActionOutcome: Decodable, Hashable {
    var headline: String
    var lines: [AgentTaskActionLine]
    var url: String?

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        headline = c.value(.headline) ?? ""
        lines = c.list(.lines)
        url = c.value(.url)
    }

    enum CodingKeys: String, CodingKey { case headline, lines, url }
}

/// One proposal: proposed, then running and done or failed (or cancelled).
struct AgentTaskActionRun: Decodable, Hashable, Identifiable {
    var id: String
    var action: String
    var label: String
    var status: String
    var preview: AgentTaskActionPreview?
    var confirmLabel: String
    var result: AgentTaskActionOutcome?
    var error: String?
    var finishedAt: Date?

    enum CodingKeys: String, CodingKey {
        case id, action, label, status, preview, result, error
        case confirmLabel = "confirm_label"
        case finishedAt = "finished_at"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(String.self, forKey: .id)
        action = c.value(.action) ?? ""
        label = c.value(.label) ?? action
        status = c.value(.status) ?? "proposed"
        preview = c.value(.preview)
        confirmLabel = c.value(.confirmLabel) ?? "Go ahead"
        result = c.value(.result)
        error = c.value(.error)
        finishedAt = (c.value(.finishedAt) as String?).flatMap { parseMWDate($0) }
    }

    var isProposed: Bool { status == "proposed" }
    var isFinished: Bool { status == "done" || status == "failed" }
}

struct IntakeFormField: Codable, Hashable, Identifiable {
    var key: String
    var label: String
    /// text, number, money, date, time, select, multi_select, boolean,
    /// location, list, file, consent.
    var type: String
    var required: Bool
    var help: String
    var options: [String]
    var accept: [String]
    var maxCount: Int
    var maxBytes: Int
    var optional: Bool
    var initial: String

    var id: String { key }

    enum CodingKeys: String, CodingKey {
        case key, label, type, required, help, options, accept, optional, value
        case maxCount = "max_count"
        case maxBytes = "max_bytes"
    }

    init(key: String, label: String, type: String, required: Bool = false, options: [String] = [],
         accept: [String] = [], maxCount: Int = 1, maxBytes: Int = 0, optional: Bool = false) {
        self.key = key; self.label = label; self.type = type; self.required = required; self.help = ""
        self.options = options; self.accept = accept; self.maxCount = maxCount; self.maxBytes = maxBytes
        self.optional = optional; self.initial = ""
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        key = try c.decode(String.self, forKey: .key)
        label = c.value(.label) ?? key
        type = c.value(.type) ?? "text"
        required = c.value(.required) ?? false
        help = c.value(.help) ?? ""
        options = c.list(.options)
        accept = c.list(.accept)
        maxCount = c.value(.maxCount) ?? 1
        maxBytes = c.value(.maxBytes) ?? 0
        optional = c.value(.optional) ?? false
        initial = IntakeFormField.text(of: (c.value(.value) as AnyCodable?)?.value)
    }

    // Message metadata is Codable as a whole, so the field writes back what it read.
    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(key, forKey: .key)
        try c.encode(label, forKey: .label)
        try c.encode(type, forKey: .type)
        try c.encode(required, forKey: .required)
        try c.encode(help, forKey: .help)
        try c.encode(options, forKey: .options)
        try c.encode(accept, forKey: .accept)
        try c.encode(maxCount, forKey: .maxCount)
        try c.encode(maxBytes, forKey: .maxBytes)
        try c.encode(optional, forKey: .optional)
        if !initial.isEmpty { try c.encode(initial, forKey: .value) }
    }

    static func text(of value: Any?) -> String {
        switch value {
        case let s as String: return s
        case let b as Bool: return b ? "yes" : "no"
        case let i as Int: return String(i)
        case let d as Double: return d.rounded() == d ? String(Int(d)) : String(d)
        case let list as [AnyCodable]: return list.map { text(of: $0.value) }.joined(separator: ", ")
        default: return ""
        }
    }
}

struct IntakeFormKnown: Codable, Hashable {
    var key: String
    var label: String
    var shown: String
}

struct IntakeFormConsent: Codable, Hashable {
    var version: String
    var title: String
    var body: [String]
}

/// The form itself (`view.form` on an `ask_form` prompt).
struct IntakeForm: Codable, Hashable {
    var playbook: String
    var label: String
    var title: String
    var directive: String
    var fields: [IntakeFormField]
    var known: [IntakeFormKnown]
    var consent: IntakeFormConsent?
    var units: Int
    var submitLabel: String

    enum CodingKeys: String, CodingKey {
        case playbook, label, title, directive, fields, known, consent, units
        case submitLabel = "submit_label"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        playbook = c.value(.playbook) ?? ""
        label = c.value(.label) ?? ""
        title = c.value(.title) ?? ""
        directive = c.value(.directive) ?? ""
        fields = c.list(.fields)
        known = c.list(.known)
        consent = c.value(.consent)
        units = c.value(.units) ?? 0
        submitLabel = c.value(.submitLabel) ?? "Start"
    }
}

/// Turning what the person typed into the values the server takes, field by
/// field, with what is wrong in their terms. Files are sent as input ids.
enum IntakeFormValues {
    enum Problem: Equatable {
        case missing(String)
        case invalid(String)

        var message: String {
            switch self {
            case .missing(let label): return "\(label) is needed."
            case .invalid(let label): return "\(label) doesn't look right."
            }
        }
    }

    /// (values to send, problems). Empty text is "not given".
    static func build(_ fields: [IntakeFormField], text: [String: String], files: [String: [String]] = [:])
        -> (values: [String: AnyCodable], problems: [Problem]) {
        var values: [String: AnyCodable] = [:]
        var problems: [Problem] = []
        for field in fields {
            if field.type == "file" {
                if field.required && (files[field.key] ?? []).isEmpty { problems.append(.missing(field.label)) }
                continue
            }
            if field.type == "consent" { continue }
            let raw = (text[field.key] ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            if raw.isEmpty {
                if field.required { problems.append(.missing(field.label)) }
                continue
            }
            if let value = parse(field, raw) {
                values[field.key] = value
            } else {
                problems.append(.invalid(field.label))
            }
        }
        return (values, problems)
    }

    static func parse(_ field: IntakeFormField, _ raw: String) -> AnyCodable? {
        switch field.type {
        case "number", "money":
            let cleaned = raw.replacingOccurrences(of: ",", with: "").replacingOccurrences(of: "$", with: "")
                .trimmingCharacters(in: .whitespaces).lowercased()
            let multiplier: Double = cleaned.hasSuffix("k") ? 1_000 : 1
            let digits = cleaned.hasSuffix("k") ? String(cleaned.dropLast()) : cleaned
            guard let number = Double(digits), number.isFinite, number >= 0 else { return nil }
            return AnyCodable(number * multiplier)
        case "date":
            let formatter = DateFormatter()
            formatter.locale = Locale(identifier: "en_US_POSIX")
            formatter.dateFormat = "yyyy-MM-dd"
            return formatter.date(from: raw) == nil ? nil : AnyCodable(raw)
        case "time":
            let parts = raw.split(separator: ":")
            guard parts.count == 2, let h = Int(parts[0]), let m = Int(parts[1]), (0..<24).contains(h), (0..<60).contains(m)
            else { return nil }
            return AnyCodable(String(format: "%02d:%02d", h, m))
        case "boolean":
            switch raw.lowercased() {
            case "yes", "true": return AnyCodable(true)
            case "no", "false": return AnyCodable(false)
            default: return nil
            }
        case "select":
            return field.options.contains(raw) ? AnyCodable(raw) : nil
        case "list", "multi_select":
            let items = raw.split(whereSeparator: { $0 == "," || $0 == "\n" })
                .map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty }
            if field.type == "multi_select" && items.contains(where: { !field.options.contains($0) }) { return nil }
            return items.isEmpty ? nil : AnyCodable(items.map { AnyCodable($0) })
        default:
            return AnyCodable(raw)
        }
    }
}

struct IntakeFormAnswer: Encodable {
    let values: [String: AnyCodable]
    let inputIds: [String]
    let consentVersion: String?

    enum CodingKeys: String, CodingKey {
        case values
        case inputIds = "input_ids"
        case consentVersion = "consent_version"
    }
}

/// A task (and one of its findings) for Tasks to open next (`openTasks`).
struct TasksFocus: Equatable {
    var taskId: String?
    var itemId: String? = nil
    /// A job search to open (a chat card, an old link), and one of its jobs.
    var jobSearchId: String? = nil
    var leadId: String? = nil
}

/// A new Espresso conversation to start a task in, with the directive drafted.
struct AssistantTaskContext: AssistantHandoff {
    let id = UUID()
    let owner: String
    let directive: String
    /// Set when asking about an existing task (and one of its findings).
    let taskId: String?
    let itemId: String?

    var conversationTitle: String {
        String((taskId == nil ? "Task: \(directive)" : "About a task").prefix(100))
    }

    var prompt: String {
        guard let taskId else { return directive }
        if let itemId {
            return "Help me with the finding \(itemId) in my task \(taskId). Read the task first.\n\nMy instructions: "
        }
        return "Help me with my task \(taskId). Read it first.\n\nMy instructions: "
    }
}
