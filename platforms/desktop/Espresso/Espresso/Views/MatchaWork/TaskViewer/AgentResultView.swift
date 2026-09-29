import SwiftUI
import AppKit

/// The agent card's result page inside the ticket viewer: the newest round's
/// structured result (top pick with photos, rating, review quotes and buy
/// links; alternatives; sources), a round switcher, the live status line while
/// a run works, and "Run again" after a failure. Photos are server-rehosted
/// CDN URLs — never a retailer's own image URL.
struct AgentResultView: View {
    let projectId: String
    let task: MWProjectTask
    let canEdit: Bool

    @State private var runs: [MWAgentRun]?
    @State private var purchases: [MWAgentPurchase] = []
    @State private var selectedRunId: String?
    @State private var busy = false
    @State private var errorText: String?

    private var live: Bool { runs?.contains(where: \.isLive) ?? false }
    private var doneRuns: [MWAgentRun] { (runs ?? []).filter { $0.status == "done" && $0.result != nil } }
    private var shown: MWAgentRun? { doneRuns.first(where: { $0.id == selectedRunId }) ?? doneRuns.first }
    /// Any open column with nothing working on it: a failed run, a card moved
    /// back by hand, or a redirect whose run the queue refused (its note is
    /// saved on the card).
    private var canRerun: Bool {
        canEdit && !live && ["todo", "in_progress", "changes_requested"].contains(task.boardColumn)
    }
    private var waitingOnRedirect: Bool {
        !live && task.boardColumn == "changes_requested" && runs?.first?.status != "failed"
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Label("Espresso agent", systemImage: "sparkle.magnifyingglass")
                    .font(.ticket(size: 11))
                    .foregroundColor(.secondary)
                Spacer()
                if doneRuns.count > 1 {
                    Picker("", selection: Binding(
                        get: { shown?.id ?? "" },
                        set: { selectedRunId = $0 }
                    )) {
                        ForEach(doneRuns) { run in Text("Round \(run.round)").tag(run.id) }
                    }
                    .pickerStyle(.segmented)
                    .fixedSize()
                }
            }

            if runs == nil {
                HStack(spacing: 6) {
                    ProgressView().controlSize(.small)
                    Text("Loading the agent's result…").font(.ticket(size: 11)).foregroundColor(.secondary)
                }
            } else if live {
                HStack(spacing: 6) {
                    ProgressView().controlSize(.small)
                    Text(task.progressNote ?? "Working on it…").font(.ticket(size: 11)).foregroundColor(.secondary)
                }
            } else if runs?.first?.status == "failed" {
                Text(task.progressNote ?? "The last run stopped before finishing.")
                    .font(.ticket(size: 11)).foregroundColor(.orange)
            } else if runs?.isEmpty == true {
                Text("The agent hasn't run on this card yet.").font(.ticket(size: 11)).foregroundColor(.secondary)
            }
            if waitingOnRedirect, runs != nil {
                Text("Your note is saved, but the agent isn't working on it yet. Run again to start.")
                    .font(.ticket(size: 11)).foregroundColor(.secondary)
            }

            if let result = shown?.result {
                AgentResultBody(result: result)
            }
            if !purchases.isEmpty {
                AgentPurchasesView(purchases: purchases)
            }

            if let errorText {
                Text(errorText).font(.ticket(size: 11)).foregroundColor(.orange)
            }
            if canRerun {
                Button {
                    Task { await rerun() }
                } label: {
                    Label(busy ? "Starting…" : "Run again", systemImage: "arrow.counterclockwise")
                        .font(.ticket(size: 11))
                }
                .disabled(busy)
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.primary.opacity(0.025))
        .cornerRadius(8)
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(Color.primary.opacity(0.1), lineWidth: 0.5))
        // Reload when the card changes (a board event moved it or updated its
        // status line), and poll while a run is live.
        .task(id: "\(task.boardColumn)|\(task.progressNote ?? "")") { await load() }
        .task(id: live) {
            guard live else { return }
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 4_000_000_000)
                await load()
            }
        }
    }

    private func load() async {
        do {
            let res = try await MatchaWorkService.shared.agentRuns(projectId: projectId, taskId: task.id)
            runs = res.runs
            purchases = res.purchases ?? []
        } catch {
            errorText = error.localizedDescription
            if runs == nil { runs = [] }
        }
    }

    private func rerun() async {
        busy = true
        errorText = nil
        defer { busy = false }
        do {
            _ = try await MatchaWorkService.shared.rerunAgent(projectId: projectId, taskId: task.id)
            await load()
        } catch let error as APIError {
            if error.planRequirement != nil {
                errorText = "Agent cards need the Pro plan."
            } else {
                errorText = error.agentRunLimitMessage ?? error.localizedDescription
            }
        } catch {
            errorText = error.localizedDescription
        }
    }
}

/// Purchases approved in the project chat. v1 records a handoff and charges
/// nothing; the person finishes checkout at the link.
private struct AgentPurchasesView: View {
    let purchases: [MWAgentPurchase]

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Label("Purchases", systemImage: "cart").font(.ticket(size: 11)).foregroundColor(.secondary)
            ForEach(purchases) { purchase in
                HStack(spacing: 6) {
                    Text(Self.line(purchase)).font(.ticket(size: 11))
                    Text("· card ending \(purchase.cardLast4)").font(.ticket(size: 11)).foregroundColor(.secondary)
                    if purchase.status == "test_charged" {
                        Text("· Stripe test charge succeeded").font(.ticket(size: 11)).foregroundColor(.green)
                    } else if purchase.status == "test_failed" {
                        Text("· Stripe test charge failed").font(.ticket(size: 11)).foregroundColor(.orange)
                            .help(purchase.chargeError ?? "")
                    }
                    Spacer()
                    if let url = URL(string: purchase.checkoutUrl),
                       ["http", "https"].contains(url.scheme?.lowercased() ?? "") {
                        Button("Checkout") { NSWorkspace.shared.open(url) }
                            .controlSize(.small)
                    }
                }
            }
            Text("Approved in chat. No real money moves: test charges run in Stripe test mode, and real checkout happens at the link.")
                .font(.ticket(size: 10)).foregroundColor(.secondary)
        }
        .padding(8)
        .overlay(RoundedRectangle(cornerRadius: 6).stroke(Color.primary.opacity(0.1), lineWidth: 0.5))
    }

    private static func line(_ purchase: MWAgentPurchase) -> String {
        var text = purchase.itemName
        if let retailer = purchase.retailer, !retailer.isEmpty { text += " at \(retailer)" }
        if let amount = purchase.amount {
            text += " · " + amount.formatted(.currency(code: purchase.currency ?? "USD"))
        }
        return text
    }
}

/// Section Markdown with every link that isn't plain http(s) stripped. The
/// server already removes links and images the run never saw; this is the
/// second lock, because `Text` opens a link of ANY scheme (file:, custom app
/// URL schemes) on click.
private func safeMarkdown(_ markdown: String) -> AttributedString {
    var attributed = (try? AttributedString(
        markdown: markdown,
        options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace)
    )) ?? AttributedString(markdown)
    for run in Array(attributed.runs) {
        guard let link = run.link else { continue }
        let scheme = link.scheme?.lowercased()
        if scheme != "https" && scheme != "http" {
            attributed[run.range].link = nil
        }
    }
    return attributed
}

private func openExternal(_ string: String) {
    guard let url = URL(string: string), let scheme = url.scheme?.lowercased(),
          scheme == "https" || scheme == "http" else { return }
    NSWorkspace.shared.open(url)
}

private func host(_ string: String) -> String {
    (URL(string: string)?.host ?? string).replacingOccurrences(of: "www.", with: "")
}

private func money(_ amount: Double, _ currency: String) -> String {
    amount.formatted(.currency(code: currency.isEmpty ? "USD" : currency))
}

struct AgentResultBody: View {
    let result: MWAgentResult

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if let changes = result.changesFromPrevious, !changes.isEmpty {
                (Text("What changed: ").bold() + Text(changes))
                    .font(.ticket(size: 11))
                    .foregroundColor(.blue)
                    .padding(8)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(Color.blue.opacity(0.08))
                    .cornerRadius(6)
            }
            Text(result.headline).font(.ticket(size: 15)).bold()
            Text(result.summary).font(.ticket(size: 12)).foregroundColor(.secondary)
                .fixedSize(horizontal: false, vertical: true)

            if let pick = result.topPick {
                AgentPickCard(pick: pick, hero: true)
            }
            if !result.criteria.isEmpty {
                VStack(alignment: .leading, spacing: 3) {
                    Text("What mattered").font(.ticket(size: 11)).foregroundColor(.secondary)
                    ForEach(result.criteria, id: \.self) { c in
                        (Text(c.name).bold() + Text(c.why.isEmpty ? "" : " — \(c.why)"))
                            .font(.ticket(size: 11))
                    }
                }
            }
            if !result.alternatives.isEmpty {
                Text("Alternatives").font(.ticket(size: 11)).foregroundColor(.secondary)
                ForEach(result.alternatives, id: \.self) { AgentPickCard(pick: $0, hero: false) }
            }
            ForEach(result.sections, id: \.self) { section in
                VStack(alignment: .leading, spacing: 3) {
                    if !section.heading.isEmpty { Text(section.heading).font(.ticket(size: 12)).bold() }
                    Text(safeMarkdown(section.bodyMd))
                        .font(.ticket(size: 12))
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            ForEach(result.caveats, id: \.self) { caveat in
                Text("• \(caveat)").font(.ticket(size: 11)).foregroundColor(.secondary)
            }
            HStack(spacing: 8) {
                Text("Confidence: \(result.confidence)").font(.ticket(size: 10)).foregroundColor(.secondary)
                ForEach(result.sources, id: \.self) { source in
                    Button(source.title.isEmpty ? host(source.url) : source.title) { openExternal(source.url) }
                        .buttonStyle(.link)
                        .font(.ticket(size: 10))
                        .lineLimit(1)
                }
            }
        }
    }
}

private struct AgentPickCard: View {
    let pick: MWAgentPick
    let hero: Bool
    @State private var imageIndex = 0

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            if hero {
                Text("TOP PICK").font(.ticket(size: 9)).bold().foregroundColor(.green)
            }
            HStack(alignment: .top, spacing: 12) {
                if pick.images.indices.contains(imageIndex) {
                    let image = pick.images[imageIndex]
                    VStack(spacing: 4) {
                        AsyncImage(url: URL(string: image.url)) { phase in
                            if let img = phase.image {
                                img.resizable().scaledToFit()
                            } else {
                                Color.primary.opacity(0.05)
                            }
                        }
                        .frame(width: hero ? 140 : 72, height: hero ? 140 : 72)
                        .background(Color.white)
                        .cornerRadius(6)
                        .onTapGesture { openExternal(image.pageUrl) }
                        .help(image.alt)
                        if pick.images.count > 1 {
                            HStack(spacing: 4) {
                                ForEach(pick.images.indices, id: \.self) { i in
                                    Circle()
                                        .fill(i == imageIndex ? Color.primary : Color.primary.opacity(0.2))
                                        .frame(width: 5, height: 5)
                                        .onTapGesture { imageIndex = i }
                                }
                            }
                        }
                    }
                }
                VStack(alignment: .leading, spacing: 5) {
                    Text(pick.name).font(.ticket(size: hero ? 14 : 12)).bold()
                    HStack(spacing: 10) {
                        if !pick.brand.isEmpty { Text(pick.brand).font(.ticket(size: 11)).foregroundColor(.secondary) }
                        if let price = pick.price {
                            Button(money(price.amount, price.currency)) { openExternal(price.sourceUrl) }
                                .buttonStyle(.plain).font(.ticket(size: 11))
                        }
                        if let rating = pick.rating {
                            Button {
                                openExternal(rating.sourceUrl)
                            } label: {
                                Label(
                                    String(format: "%.1f/%.0f", rating.value, rating.scale)
                                        + (rating.count.map { " (\($0.formatted()) ratings)" } ?? ""),
                                    systemImage: "star.fill"
                                )
                                .font(.ticket(size: 11))
                                .foregroundColor(.orange)
                            }
                            .buttonStyle(.plain)
                        }
                    }
                    ForEach(pick.why, id: \.self) { reason in
                        Text("• \(reason)").font(.ticket(size: 11)).fixedSize(horizontal: false, vertical: true)
                    }
                    if hero {
                        ForEach(pick.reviews, id: \.self) { review in
                            Button {
                                openExternal(review.url)
                            } label: {
                                Text("“\(review.quote)” — \(review.sourceName.isEmpty ? host(review.url) : review.sourceName)")
                                    .font(.ticket(size: 11))
                                    .foregroundColor(.secondary)
                                    .multilineTextAlignment(.leading)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                            .buttonStyle(.plain)
                        }
                    }
                    if !pick.buyLinks.isEmpty {
                        HStack(spacing: 6) {
                            ForEach(pick.buyLinks, id: \.self) { link in
                                Button {
                                    openExternal(link.url)
                                } label: {
                                    Label(
                                        (link.retailer.isEmpty ? host(link.url) : link.retailer)
                                            + (link.price.map { " · \(money($0, pick.price?.currency ?? "USD"))" } ?? ""),
                                        systemImage: "cart"
                                    )
                                    .font(.ticket(size: 11))
                                }
                                .buttonStyle(.borderedProminent)
                                .controlSize(.small)
                            }
                        }
                    }
                }
            }
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.primary.opacity(0.03))
        .cornerRadius(8)
    }
}
