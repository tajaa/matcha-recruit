import Foundation

/// Every Espresso feature that has a how-it-works guide. String values are
/// the persistence keys for "seen" — don't rename without a migration.
///
/// A new feature adds a case here and a guide in `FeatureGuide.catalog`; a new
/// sidebar section must also map to one in `Section.guide` (the switch is
/// exhaustive, so it won't compile until it does). The fixed rows above the
/// sections (the Espresso card, Tasks) open theirs from their context menus. `FeatureGuideTests` checks
/// that every guide explains both how to use it and what to expect.
enum FeatureGuideID: String, CaseIterable, Identifiable {
    case assistant
    case tasks
    case jobSearch = "job_search"
    case channels
    case workspaces
    case reviewBoard = "review_board"
    case agentCards = "agent_cards"
    case sales
    case threads
    case journals
    case productivity
    case calendar
    case email

    var id: String { rawValue }

    /// The review how-to shipped before this framework, behind one
    /// install-wide flag. Anyone who already saw it shouldn't see it again.
    var legacySeenKey: String? {
        self == .reviewBoard ? "werk-review-wizard-seen" : nil
    }
}

/// One feature's guide: a few pages, each tagged with the question it answers.
struct FeatureGuide {
    enum Stage: Equatable {
        case overview, howTo, expect

        var label: String {
            switch self {
            case .overview: return "WHAT IT IS"
            case .howTo: return "HOW TO USE IT"
            case .expect: return "WHAT TO EXPECT"
            }
        }
    }

    struct Page {
        let stage: Stage
        let icon: String
        let title: String
        var body: String = ""
        /// Steps on a how-to page (numbered), facts elsewhere (checked).
        var points: [String] = []
    }

    let id: FeatureGuideID
    /// The feature's name as the sidebar and menus show it.
    let name: String
    let pages: [Page]

    static func guide(for id: FeatureGuideID) -> FeatureGuide {
        catalog[id] ?? FeatureGuide(id: id, name: id.rawValue, pages: [])
    }

    static let catalog: [FeatureGuideID: FeatureGuide] = Dictionary(
        uniqueKeysWithValues: all.map { ($0.id, $0) })
}

extension SidebarSectionOrderStore.Section {
    /// The guide for this sidebar section. Exhaustive on purpose: a section
    /// can't ship without one.
    var guide: FeatureGuideID {
        switch self {
        case .channels: return .channels
        case .projects: return .workspaces
        case .journals: return .journals
        case .productivity: return .productivity
        case .calendar: return .calendar
        case .threads: return .threads
        case .email: return .email
        }
    }
}

/// Whether someone has seen a guide. Per person, so a second account on the
/// same Mac still gets each guide once.
enum FeatureGuideSeen {
    static func key(_ id: FeatureGuideID, userId: String) -> String {
        "mw-feature-guide-seen-v1:\(id.rawValue):\(userId)"
    }

    static func isSeen(_ id: FeatureGuideID, userId: String,
                       defaults: UserDefaults = .standard) -> Bool {
        if defaults.bool(forKey: key(id, userId: userId)) { return true }
        if let legacy = id.legacySeenKey, defaults.bool(forKey: legacy) { return true }
        return false
    }

    static func markSeen(_ id: FeatureGuideID, userId: String,
                         defaults: UserDefaults = .standard) {
        defaults.set(true, forKey: key(id, userId: userId))
    }
}

// MARK: - The guides
//
// Plain words, no jargon. Every number or promise here must match what the
// code does; a guide that oversells is worse than none. Limits the server owns
// (plan caps, monthly counts) point to where the app shows the live number
// rather than repeating it.

extension FeatureGuide {
    static let all: [FeatureGuide] = [
        assistant, tasks, jobSearch, channels, workspaces, reviewBoard, agentCards, sales,
        threads, journals, productivity, calendar, email,
    ]

    static let assistant = FeatureGuide(id: .assistant, name: "Espresso", pages: [
        Page(stage: .overview, icon: "sparkles",
             title: "Your private assistant",
             body: "A conversation only you can see. Espresso researches and compares things on the web, and once you switch them on it can work with your email, calendar, sales campaigns, job searches and restaurant bookings."),
        Page(stage: .howTo, icon: "text.bubble.fill",
             title: "Ask for anything",
             points: [
                "Type a request. No @mention needed.",
                "Click What it can do to see every ability. Switch one on to read what it shares, then agree.",
                "Pick the AI model from the model menu if you like.",
                "Start a New session to keep a separate topic apart.",
             ]),
        Page(stage: .expect, icon: "checkmark.shield.fill",
             title: "When it acts, and when it asks",
             points: [
                "Web research and shopping comparisons need no setup, and neither do flight searches and page screenshots where they're offered. It can't book flights.",
                "With an ability on, it does what you clearly asked, such as emailing someone you named or booking a place you named.",
                "Anything involving a person or site you didn't mention, it asks about first. Yes does exactly what the card showed. No cancels.",
                "Each ability says whether its changes are live or only previewed.",
             ]),
        Page(stage: .expect, icon: "hand.raised.fill",
             title: "What it never does",
             points: [
                "It never deletes email, and it ignores instructions written inside emails.",
                "It never pays for a booking. If a booking needs a card, a login or a captcha, it gives you the link instead.",
                "Its sales and job search tools only draft. They send nothing.",
             ]),
        Page(stage: .expect, icon: "gauge.with.dots.needle.33percent",
             title: "Limits",
             points: [
                "For personal accounts on Pro. The conversation header shows how many requests you have left today.",
                "It works on one request at a time, and a request can take a few minutes.",
                "Saying yes to something it asked about uses a request.",
                "What you ask goes to the AI model provider you picked.",
             ]),
    ])

    static let channels = FeatureGuide(id: .channels, name: "Channels", pages: [
        Page(stage: .overview, icon: "number",
             title: "Chat rooms for your people",
             body: "Real-time channels for talking with others: open communities, private groups, or paid channels for subscribers."),
        Page(stage: .howTo, icon: "plus.bubble.fill",
             title: "Start or join one",
             points: [
                "Click New Channel. Give it a name, a description and a category, and choose public or private.",
                "To join, click a channel under Open to join and press Join. Paid channels show View, and Subscribe pays in your browser.",
                "Chat in real time: attach files, reply and react.",
                "Use Invite in a channel's header to add people. Click the member count to manage them.",
             ]),
        Page(stage: .howTo, icon: "video.fill",
             title: "Calls and going live",
             points: [
                "In a channel you own, click Call and choose whether all members can join or only people you invite.",
                "Go Live starts a video or audio broadcast to the channel.",
                "Members see a banner and join from there.",
             ]),
        Page(stage: .expect, icon: "info.circle.fill",
             title: "Good to know",
             points: [
                "Channels and chat are free on every plan.",
                "Starting a call or going live needs Pro. Joining is free. A call holds up to 4 people, and a channel runs one call or broadcast at a time.",
                "Private channels are invitation only.",
                "On Pro, a personal account can make a paid channel with a monthly price. Members pay through Stripe.",
                "@espresso only answers inside a workspace's chat.",
             ]),
    ])

    static let workspaces = FeatureGuide(id: .workspaces, name: "Workspaces", pages: [
        Page(stage: .overview, icon: "square.grid.2x2.fill",
             title: "One place per piece of work",
             body: "A workspace holds a document you write with AI, a presentation, a blog post, a hiring pipeline, or a shared board you run with collaborators."),
        Page(stage: .howTo, icon: "plus.square.fill",
             title: "Start one",
             points: [
                "Click New Workspace and pick a type: General, Presentation, Recruiting, Collaborative or Blog Post.",
                "General and Presentation give you sections to edit, a chat to ask for changes, and a preview.",
                "Collaborative walks you through setup, then opens a board with chat, files, media, elements and notes.",
             ]),
        Page(stage: .howTo, icon: "rectangle.3.group.fill",
             title: "Work on a shared board",
             points: [
                "Type into Describe a task to draft… and click Draft. Nothing is saved until you click Create.",
                "Tickets move Todo → In Progress → Review → Done.",
                "In the Chat tab, ask @espresso how something in your connected repo works. The answer links to the source.",
                "Ask @espresso to find something to buy, and it researches it as an agent card on the board.",
             ]),
        Page(stage: .expect, icon: "person.2.badge.gearshape.fill",
             title: "Plans and sharing",
             points: [
                "General, Presentation and Blog Post need Lite or higher. Collaborative and Recruiting need Pro.",
                "Your company and the collaborators you add can see a workspace. Viewers and commenters can only read.",
                "@espresso only reads your repo. It never changes your code.",
                "Drafting tasks and @espresso answers use your AI allowance.",
             ]),
    ])

    static let threads = FeatureGuide(id: .threads, name: "Threads", pages: [
        Page(stage: .overview, icon: "bubble.left.and.bubble.right.fill",
             title: "Chat your way to a document",
             body: "A thread is a conversation with AI that can produce a document as you go: a letter, a plan, a workbook, a presentation. Refine it by asking."),
        Page(stage: .howTo, icon: "plus.message.fill",
             title: "Use it",
             points: [
                "Click New Thread and type what you need.",
                "Once there's a document, its preview opens beside the chat. Ask for changes, or go back with version history.",
                "Choose the AI model from the model menu.",
                "Click Finalize when it's done. That locks the thread and removes the watermark.",
             ]),
        Page(stage: .expect, icon: "gauge.with.dots.needle.50percent",
             title: "What to expect",
             points: [
                "Each thread shows the tokens it has used, and the chart button shows your overall usage.",
                "Every plan has an AI allowance that refills every 12 hours, larger on paid plans. If you run out, you'll see when it resets.",
                "A reply that has started always finishes.",
                "The most capable model needs Pro.",
                "On a business account, everyone in your company can see your threads.",
             ]),
    ])

    static let sales = FeatureGuide(id: .sales, name: "Sales campaigns", pages: [
        Page(stage: .overview, icon: "megaphone.fill",
             title: "Outreach you approve before it goes",
             body: "A campaign is a private list of prospects with research and draft emails. Espresso can research and draft. You review and send in batches from your own Gmail."),
        Page(stage: .howTo, icon: "person.crop.rectangle.stack.fill",
             title: "Run a campaign",
             points: [
                "On a collaborative workspace's board, switch to Pipeline, then Campaigns.",
                "Click New campaign. Say who to find, what you offer, and your email footer.",
                "Import contacts (paste or CSV, up to 1,000), or choose Research and draft with Espresso.",
                "Open a prospect to edit its draft, or use Draft with template.",
                "Select drafts (up to 50 at a time), then Review and send.",
             ]),
        Page(stage: .expect, icon: "paperplane.fill",
             title: "Sending is always yours",
             points: [
                "Espresso researches and drafts, but never sends. Nothing goes out until you review a batch and press Send.",
                "If anything in a batch changes after your review, sending stops until you review it again.",
                "Emails go from your connected Gmail one at a time, about 15 seconds apart, within hourly and daily caps that leave room for your own mail.",
                "Your footer needs an opt-out line and a postal address. People marked do-not-contact are always skipped.",
                "If a send can't be confirmed, it isn't retried. Check Gmail's Sent folder and mark it.",
             ]),
        Page(stage: .expect, icon: "lock.fill",
             title: "Plans and privacy",
             points: [
                "Collaborative workspaces need Pro. Research and draft with Espresso also needs the Espresso assistant.",
                "Only you see a campaign's contacts.",
             ]),
    ])

    static let tasks = FeatureGuide(id: .tasks, name: "Tasks", pages: [
        Page(stage: .overview, icon: "checklist",
             title: "Send Espresso off to do the legwork",
             body: "Ask for something that takes real searching, like “find me a one-bedroom in SF under $3,500 that takes dogs.” Espresso works on it in the background and keeps what it finds here, with where each fact came from."),
        Page(stage: .howTo, icon: "plus.bubble.fill",
             title: "Start one",
             points: [
                "Ask Espresso in its chat, or type what you want in the box at the top of Tasks and click Ask Espresso.",
                "If it needs more, like a move-in date, it posts a short form in the chat. Fill it in, add files if it asks for them, and start it. Typing your answer works too.",
                "Job searches live here too: click New job search, or ask Espresso for one.",
                "Running tasks show as a count next to Tasks in the sidebar, with a dot when one needs you.",
             ]),
        Page(stage: .howTo, icon: "slider.horizontal.3",
             title: "Work with what it found",
             points: [
                "Open a finding to see its facts. Verified ones show the quote and the page they came from.",
                "Save, Choose or Dismiss findings, add notes, or Ask Espresso about one.",
                "Refine changes what it's looking for. Search more looks for more like these. Make document writes it all into a note in Journals.",
             ]),
        Page(stage: .expect, icon: "clock.fill",
             title: "What to expect",
             points: [
                "A task takes a few minutes. You can leave: you'll get a notification when it's done or needs you.",
                "It only researches. It doesn't buy, book, sign up or contact anyone.",
                "Only a fact it verified can rule a finding out. One it couldn't check is marked Unconfirmed and ranked after the confirmed ones.",
                "Up to \(tasksRunningAtOnce) tasks run at once.",
             ]),
        Page(stage: .expect, icon: "lock.fill",
             title: "Units and privacy",
             points: [
                "A new task uses units from your monthly allowance, shown at the bottom of Tasks. Search more uses 1; Refine and Make document are free. A task that fails doesn't count.",
                "Deleting a task removes what it found, but it still counts for the month.",
                "Files you give it are kept privately: only you can open them, and only Espresso's AI models read them.",
             ]),
    ])

    /// Tasks one person can have running (`MAX_LIVE` in agent_tasks/enqueue.py).
    static let tasksRunningAtOnce = 2

    static let agentCards = FeatureGuide(id: .agentCards, name: "Agent cards", pages: [
        Page(stage: .overview, icon: "wand.and.stars",
             title: "Hand off an errand",
             body: "An agent card researches something for you on the web, like “find me the best organic lip balm,” and comes back with picks, photos, reviews and where to buy."),
        Page(stage: .howTo, icon: "plus.rectangle.on.rectangle",
             title: "Make one",
             points: [
                "On a collaborative workspace's board, click + on a column and choose Agent.",
                "Name the errand, and add anything it should know.",
                "It starts right away. Open the card to watch its progress and read the result.",
                "Approve it, or Send back with a note and it tries again with your note.",
                "In a workspace chat, “@espresso find me … to buy” makes one too.",
             ]),
        Page(stage: .expect, icon: "clock.fill",
             title: "What to expect",
             points: [
                "It only researches. It doesn't buy, sign up or fill in forms.",
                "A run takes a few minutes and moves the card from To do to In progress to Review.",
                "Each run, including each send-back, counts toward your plan's monthly agent runs (Pro and up). Failed runs don't count.",
                "If a run fails, Run again is on the card.",
             ]),
    ])

    static let jobSearch = FeatureGuide(id: .jobSearch, name: "Job search", pages: [
        Page(stage: .overview, icon: "briefcase.fill",
             title: "A serious search from one sentence",
             body: "Tell Espresso what you're after, like “COO roles across the US — I care most about salary, bonus and equity.” It searches live job listings, ranks them by what matters to you, and drafts how to go after the best ones."),
        Page(stage: .howTo, icon: "plus.circle.fill",
             title: "Start a search",
             points: [
                "In Tasks, click New job search. Your searches are listed there with your other tasks.",
                "Describe the job in your own words. Add titles, places, remote or on-site, and a minimum base if you have one.",
                "Choose whether Espresso may use your saved résumé to judge fit and write the drafts.",
                "Read what's shared and where, tick I agree, then Start search.",
                "If you have Tasks, you can also ask Espresso in its chat. It asks for what it needs with a short form.",
             ]),
        Page(stage: .expect, icon: "clock.fill",
             title: "Give it a few minutes",
             points: [
                "It searches Google Jobs and company job boards, drops what doesn't fit, reads the postings and ranks them.",
                "You can leave while it works. The list fills in as it goes, Cancel stops it, and you get a notification when it's done.",
                "Ranking follows What matters. Change the weights to re-rank anytime.",
             ]),
        Page(stage: .expect, icon: "dollarsign.circle.fill",
             title: "Pay is only what's posted",
             points: [
                "Every pay figure comes from the posting itself, with the line it was quoted from.",
                "A job that doesn't post pay says Not posted. It's never guessed or counted as zero, and it ranks after jobs that do.",
             ]),
        Page(stage: .expect, icon: "doc.text.fill",
             title: "Drafts you send yourself",
             points: [
                "The top \(jobSearchDraftedJobs) jobs get an approach plan, an outreach email, answers to the application's questions and a cover letter.",
                "Nothing is ever sent, applied for or submitted for you.",
                "Work authorization, sponsorship, clearance, demographic and upload questions are left for you to answer.",
                "Once a search finishes, Draft or Redraft any job from its page, up to \(jobSearchRedrafts) a search. Re-ranking and redrafting don't use up a search.",
             ]),
        Page(stage: .expect, icon: "lock.fill",
             title: "Limits and privacy",
             points: [
                "Each new search uses units from your monthly allowance, shown at the bottom of Tasks.",
                "Search terms go to the job listing services. Your résumé is used only by Espresso's AI models, never sent to job sites.",
                "Deleting a search removes its jobs and drafts, but it still counts for the month.",
             ]),
    ])

    /// How many top jobs a search drafts approaches for (the server's
    /// `APPROACH_TOP` in job_search/model_phases.py).
    static let jobSearchDraftedJobs = 8
    /// Drafts and redrafts allowed per search (`MAX_REDRAFTS` in job_search/service.py).
    static let jobSearchRedrafts = 20

    static let journals = FeatureGuide(id: .journals, name: "Journals", pages: [
        Page(stage: .overview, icon: "book.closed.fill",
             title: "Your writing space",
             body: "Notes in folders, with templates for blogs, to-do lists, novels and screenplays. Everything saves as you type."),
        Page(stage: .howTo, icon: "square.and.pencil",
             title: "Write",
             points: [
                "Click New note (⌘N), or use the arrow next to compose to start from a template.",
                "Type / to add a block. The toolbar and shortcuts like ⌘B, ⌘I and ⌘K handle formatting.",
                "In a screenplay, Tab changes the element and Return moves on to the next one.",
                "Select text and right-click to make it a to-do or put it on today's calendar.",
             ]),
        Page(stage: .howTo, icon: "person.2.fill",
             title: "Share and publish",
             points: [
                "Click Invite and find people by name or email.",
                "The eye button switches to reading view. The share button exports or copies the journal.",
             ]),
        Page(stage: .expect, icon: "lock.fill",
             title: "Private unless you invite someone",
             points: [
                "A journal is visible only to you and the people you invite.",
                "An invite takes effect right away, and the person gets a notification and an email.",
                "Journals others share with you are under Shared with me, not in your folders.",
                "Only the journal's creator can rename it or invite people.",
                "Deleting a journal is permanent. Deleting a folder moves its journals to the top level.",
                "The Blog, Novel and Screenplay templates need Lite or higher.",
             ]),
    ])

    static let productivity = FeatureGuide(id: .productivity, name: "Productivity", pages: [
        Page(stage: .overview, icon: "checklist",
             title: "Your own to-do boards",
             body: "Simple boards with To Do, In Progress and Done columns, plus a calendar of dated cards. Your boards are private to you."),
        Page(stage: .howTo, icon: "square.grid.3x1.below.line.grid.1x2",
             title: "Track your to-dos",
             points: [
                "Click + next to Boards to make a board.",
                "Click + on a column, type a title and press Return.",
                "Drag cards between columns as the work moves.",
                "Right-click a card to rename it, put it on today's calendar, or delete it.",
                "Switch to Calendar to see dated cards by month. Drag a card to another day to move it.",
             ]),
        Page(stage: .expect, icon: "tray.and.arrow.down.fill",
             title: "Where cards come from",
             points: [
                "My To-Dos is made for you the first time something is sent to it, and it can't be deleted.",
                "Right-clicking selected text in a journal can send it here as a to-do.",
                "Reminders you ask the Espresso assistant for land here as dated cards.",
                "Dated cards from every board also show in Calendar.",
                "Deleting a board deletes its cards too, and it can't be undone.",
             ]),
    ])

    static let calendar = FeatureGuide(id: .calendar, name: "Calendar", pages: [
        Page(stage: .overview, icon: "calendar",
             title: "Everything dated, in one place",
             body: "Your Espresso events, dated to-dos from Productivity, and the Google and Apple calendars you connect."),
        Page(stage: .howTo, icon: "calendar.badge.plus",
             title: "Use it",
             points: [
                "Move with ‹ Today › (⌘← ⌘T ⌘→), and switch between Month and Week.",
                "Click New event (⌘N) to add one. Click one of your events to edit or delete it.",
                "Click a dated to-do to mark it done.",
                "Click Calendars to connect a Google account or choose Apple calendars on this Mac.",
             ]),
        Page(stage: .expect, icon: "link",
             title: "Connected calendars",
             points: [
                "Your Espresso events are private. Adding one never invites anyone.",
                "Google events show here read-only, and clicking one opens it in Google. Email and Calendar share one Google connection.",
                "The Apple calendars you choose sync from this Mac about every 30 seconds while Espresso is open. Their titles, times, places and notes are copied to Espresso. One Mac at a time.",
             ]),
        Page(stage: .expect, icon: "sparkles",
             title: "If the Espresso assistant has access",
             points: [
                "Once you allow it, Espresso can add, change and remove events on your Espresso and Google calendars for you.",
                "Changes to a Google event notify its attendees.",
                "It checks with you before inviting anyone you haven't named.",
             ]),
    ])

    static let email = FeatureGuide(id: .email, name: "Email", pages: [
        Page(stage: .overview, icon: "envelope.fill",
             title: "Gmail, with help",
             body: "Read your Gmail here. Espresso can summarize a message, draft a reply, pull dates into your calendar, and turn emails into board cards."),
        Page(stage: .howTo, icon: "envelope.open.fill",
             title: "Get started",
             points: [
                "Click Connect Gmail and sign in with Google in your browser.",
                "Pick Unread, Read or All mail, search, and click a message. ⌘-click or ⇧-click selects several.",
                "In a message, choose Summarize, Add to calendar, or Draft reply. You can add instructions for the reply.",
                "Send to board turns emails into a card on a shared board. Work in Espresso hands them to the assistant.",
             ]),
        Page(stage: .expect, icon: "hand.raised.fill",
             title: "Nothing happens behind your back",
             points: [
                "This screen never labels, moves, archives or marks mail as read in Gmail.",
                "Draft reply saves the draft to your Gmail Drafts right away. Nothing is sent until you press Send now.",
                "Add to calendar shows the events first. Nothing is added until you press Add, and only to your Espresso calendar.",
                "Remote images stay blocked until you click Show images.",
             ]),
        Page(stage: .expect, icon: "cpu",
             title: "AI and plans",
             points: [
                "Reading and sending are free. Summaries, sorting, drafts and calendar suggestions need Lite or higher.",
                "On those plans, new mail is sorted automatically, which sends it to the AI model. Turn it off in the … menu with Sort new mail automatically.",
             ]),
    ])

    static let reviewBoard = FeatureGuide(id: .reviewBoard, name: "Ticket review", pages: [
        Page(stage: .overview, icon: "rectangle.stack.fill",
             title: "Tickets move through rounds",
             body: "Each ticket flows Todo → In Progress → Review → Done. Sending one back from review opens a new ROUND, so each rework pass reads as its own block in the history."),
        Page(stage: .howTo, icon: "arrow.triangle.branch",
             title: "Commits check off the work",
             body: "Merge to main and the scanner reads your commits. A confident match auto-checks the subtask; a borderline one shows a ✨ suggestion chip you Accept with one tap. Nothing is ever flipped without a record."),
        Page(stage: .howTo, icon: "checkmark.seal.fill",
             title: "Review: keep or deny each item",
             body: "Open a ticket in Review. Each done item shows which commit completed it (and how sure the AI was). If it isn't really done, hit the ✗ Deny, choose Blocker or Nit, and say why — it reopens and rolls into the next round."),
        Page(stage: .expect, icon: "arrow.uturn.backward.circle.fill",
             title: "Send back, or approve",
             body: "Send back → the ticket goes to Changes Requested with your denials listed for the assignee. Approve → it moves to Done with a sign-off. On a re-review, “Since last review” shows only what changed this round."),
    ])
}
