import SwiftUI
import AppKit

/// The Espresso assistant's chat cards (server payloads: agent_runtime/):
///
/// * progress — a run working, with the steps it has taken;
/// * result   — the answer, block by block. A block type this build doesn't
///              know is skipped, never an error;
/// * receipt  — something Espresso did for the person (sent, invited, booked).
///
/// Links open in the browser and are http(s) only. Section text is rendered
/// as Markdown with every non-http(s) link stripped.
extension AgentCardMessageView {

    // MARK: - Progress

    private static let visibleSteps = 4

    @ViewBuilder
    func progressCard(_ progress: AgentRunProgress?) -> some View {
        let status = progress?.status ?? "queued"
        let working = progress?.isWorking ?? true
        let steps = progress?.steps ?? []
        let shown = showAllSteps ? steps : Array(steps.suffix(Self.visibleSteps))
        card {
            VStack(alignment: .leading, spacing: 8) {
                HStack(spacing: 6) {
                    if working {
                        ProgressView().controlSize(.small)
                    } else {
                        Image(systemName: status == "failed" ? "xmark.octagon.fill" : "checkmark.circle.fill")
                            .font(.system(size: 12))
                            .foregroundColor(status == "failed" ? .red : .green)
                    }
                    Text(progressTitle(progress, status: status, working: working))
                        .font(.system(size: 12, weight: .medium))
                        .foregroundColor(appState.themeText)
                        .fixedSize(horizontal: false, vertical: true)
                }
                if !shown.isEmpty {
                    VStack(alignment: .leading, spacing: 3) {
                        ForEach(shown, id: \.seq) { step in
                            HStack(alignment: .firstTextBaseline, spacing: 6) {
                                Image(systemName: "circle.dotted")
                                    .font(.system(size: 9))
                                    .foregroundColor(stepColor(step.status))
                                Text(step.label)
                                    .font(.system(size: 11))
                                    .foregroundColor(appState.themeTextSecondary)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                        }
                    }
                }
                if steps.count > Self.visibleSteps {
                    Button(showAllSteps ? "Show fewer" : "Show all \(steps.count) steps") {
                        showAllSteps.toggle()
                    }
                    .buttonStyle(.plain)
                    .font(.system(size: 11))
                    .foregroundColor(appState.themeTextSecondary)
                }
            }
        }
    }

    private func progressTitle(_ progress: AgentRunProgress?, status: String, working: Bool) -> String {
        if let note = progress?.note, !note.isEmpty { return note }
        if working { return status == "queued" ? "Starting\u{2026}" : "Working on it\u{2026}" }
        return status == "failed" ? "Stopped" : "Done"
    }

    private func stepColor(_ status: String) -> Color {
        switch status {
        case "ok": return .green
        case "error", "denied": return .red
        case "unknown", "held": return .orange
        default: return appState.themeTextSecondary
        }
    }

    // MARK: - Answer

    @ViewBuilder
    func resultV2Card(_ result: AgentChatResultV2) -> some View {
        card {
            VStack(alignment: .leading, spacing: 10) {
                Text(result.headline)
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(appState.themeText)
                    .fixedSize(horizontal: false, vertical: true)
                    .textSelection(.enabled)
                if !result.summary.isEmpty {
                    Text(result.summary)
                        .font(.system(size: 12))
                        .foregroundColor(appState.themeTextSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                        .textSelection(.enabled)
                }
                ForEach(Array(result.blocks.enumerated()), id: \.offset) { _, block in
                    blockView(block)
                }
                if !result.caveats.isEmpty {
                    VStack(alignment: .leading, spacing: 2) {
                        ForEach(result.caveats, id: \.self) { caveat in
                            Text("\u{2022} \(caveat)")
                                .font(.system(size: 11))
                                .foregroundColor(appState.themeTextSecondary)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                }
            }
        }
    }

    @ViewBuilder
    private func blockView(_ block: AgentResultBlock) -> some View {
        switch block {
        case .picks(let top, let alternatives):
            if let top { topPick(top) }
            if !alternatives.isEmpty {
                Divider().opacity(0.5)
                Text("ALSO COMPARED")
                    .font(.system(size: 10, weight: .semibold))
                    .tracking(0.6)
                    .foregroundColor(appState.themeTextSecondary)
                ForEach(Array(alternatives.enumerated()), id: \.offset) { _, alt in
                    alternativeRow(alt)
                }
            }
        case .sections(let sections):
            ForEach(Array(sections.enumerated()), id: \.offset) { _, section in
                VStack(alignment: .leading, spacing: 3) {
                    if !section.heading.isEmpty {
                        Text(section.heading)
                            .font(.system(size: 12, weight: .semibold))
                            .foregroundColor(appState.themeText)
                    }
                    Text(Self.safeMarkdown(section.bodyMd))
                        .font(.system(size: 12))
                        .foregroundColor(appState.themeText)
                        .fixedSize(horizontal: false, vertical: true)
                        .textSelection(.enabled)
                }
            }
        case .sources(let sources):
            let links = sources.compactMap { source in httpURL(source.url).map { (source, $0) } }
            if !links.isEmpty {
                Divider().opacity(0.5)
                VStack(alignment: .leading, spacing: 3) {
                    ForEach(Array(links.enumerated()), id: \.offset) { _, pair in
                        Button {
                            NSWorkspace.shared.open(pair.1)
                        } label: {
                            Label(pair.0.title.flatMap { $0.isEmpty ? nil : $0 } ?? pair.1.host() ?? "Source",
                                  systemImage: "link")
                                .font(.system(size: 11))
                                .lineLimit(1)
                        }
                        .buttonStyle(.plain)
                        .foregroundColor(appState.themeTextSecondary)
                    }
                }
            }
        case .emails(let items):
            ForEach(items, id: \.messageId) { item in
                itemRow(icon: "envelope", title: item.subject.isEmpty ? "(no subject)" : item.subject,
                        subtitle: item.from, detail: item.snippet)
            }
        case .events(let items):
            ForEach(items, id: \.eventId) { item in
                itemRow(icon: "calendar", title: item.title, subtitle: Self.when(item.start, item.end),
                        detail: [item.location, item.attendeeCount.flatMap { $0 > 0 ? "\($0) invited" : nil }]
                            .compactMap { $0 }.joined(separator: " \u{00B7} "))
            }
        case .flights(let flights):
            if !flights.options.isEmpty { flightRows(flights) }
        case .reservation(let booking):
            reservationView(booking)
        case .purchaseSetup(let setup):
            if !setup.steps.isEmpty { PurchaseSetupView(setup: setup) }
        case .unknown:
            EmptyView()
        }
    }

    private func itemRow(icon: String, title: String, subtitle: String, detail: String?) -> some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: icon)
                .font(.system(size: 11))
                .foregroundColor(appState.themeTextSecondary)
                .frame(width: 14)
            VStack(alignment: .leading, spacing: 1) {
                Text(title)
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundColor(appState.themeText)
                    .lineLimit(1)
                Text(subtitle)
                    .font(.system(size: 11))
                    .foregroundColor(appState.themeTextSecondary)
                    .lineLimit(1)
                if let detail, !detail.isEmpty {
                    Text(detail)
                        .font(.system(size: 11))
                        .foregroundColor(appState.themeTextSecondary.opacity(0.8))
                        .lineLimit(2)
                }
            }
            Spacer(minLength: 0)
        }
        .padding(8)
        .background(RoundedRectangle(cornerRadius: 8, style: .continuous).fill(appState.themeText.opacity(0.04)))
    }

    private func reservationView(_ booking: AgentReservation) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            HStack(spacing: 6) {
                Image(systemName: "fork.knife")
                    .font(.system(size: 11))
                    .foregroundColor(appState.themeAccent)
                Text(booking.venue)
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundColor(appState.themeText)
                Spacer(minLength: 8)
                Text(Self.reservationText(booking.status))
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundColor(booking.status == "booked" ? .green : .orange)
            }
            Text("\(booking.when) \u{00B7} party of \(booking.partySize)")
                .font(.system(size: 11))
                .foregroundColor(appState.themeTextSecondary)
            if let confirmation = booking.confirmation, !confirmation.isEmpty {
                Text("Confirmation \(confirmation)")
                    .font(.system(size: 11, design: .monospaced))
                    .foregroundColor(appState.themeText)
                    .textSelection(.enabled)
            }
            if let url = httpURL(booking.handoffUrl) {
                Button {
                    NSWorkspace.shared.open(url)
                } label: {
                    Label("Finish booking at \(url.host() ?? "the site")", systemImage: "arrow.up.right.square")
                        .font(.system(size: 12, weight: .semibold))
                }
                .buttonStyle(.bordered)
            }
        }
        .padding(10)
        .background(RoundedRectangle(cornerRadius: 12, style: .continuous).fill(appState.themeText.opacity(0.04)))
    }

    static func reservationText(_ status: String) -> String {
        switch status {
        case "booked": return "Booked"
        case "unverified": return "Submitted, not confirmed by the site"
        case "unavailable": return "That time was not available"
        case "handoff": return "Needs payment details: finish it yourself"
        case "blocked": return "The site asked for a login or a human check"
        default: return "Could not be booked"
        }
    }

    /// Section text as Markdown, with every link that is not http(s) removed.
    /// The server already strips links the run never saw; this is the second lock.
    static func safeMarkdown(_ text: String) -> AttributedString {
        let options = AttributedString.MarkdownParsingOptions(
            interpretedSyntax: .inlineOnlyPreservingWhitespace,
            failurePolicy: .returnPartiallyParsedIfPossible
        )
        guard var parsed = try? AttributedString(markdown: text, options: options) else {
            return AttributedString(text)
        }
        for run in parsed.runs {
            guard let link = run.link else { continue }
            if !["http", "https"].contains(link.scheme?.lowercased() ?? "") {
                parsed[run.range].link = nil
            }
        }
        return parsed
    }

    /// An event's time, as the person would say it. A date with no time is an
    /// all-day event and is shown as written, not shifted by the timezone.
    static func when(_ start: String, _ end: String?) -> String {
        if start.count == 10 { return start }
        guard let from = parseInstant(start) else { return end.map { "\(start) to \($0)" } ?? start }
        let day = from.formatted(.dateTime.weekday(.abbreviated).month(.abbreviated).day())
        let time = from.formatted(date: .omitted, time: .shortened)
        if let end, let to = parseInstant(end) {
            return "\(day), \(time) to \(to.formatted(date: .omitted, time: .shortened))"
        }
        return "\(day), \(time)"
    }

    private static func parseInstant(_ raw: String) -> Date? {
        let fractional = ISO8601DateFormatter()
        fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return fractional.date(from: raw) ?? ISO8601DateFormatter().date(from: raw)
    }

    // MARK: - Receipt

    @ViewBuilder
    func actionReceiptCard(_ receipt: AgentActionReceipt) -> some View {
        let tone = receiptTone(receipt.status)
        card {
            VStack(alignment: .leading, spacing: 8) {
                HStack(spacing: 6) {
                    Image(systemName: tone.icon)
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundColor(tone.color)
                    Text(receipt.title)
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundColor(appState.themeText)
                    Spacer(minLength: 8)
                    Text(tone.label.uppercased())
                        .font(.system(size: 9, weight: .bold))
                        .tracking(0.6)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(Capsule().fill(tone.color.opacity(0.16)))
                        .foregroundColor(tone.color)
                }
                actionLines(receipt.lines)
                if let note = receipt.note, !note.isEmpty {
                    Text(note)
                        .font(.system(size: 11))
                        .foregroundColor(appState.themeTextSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                if let link = receipt.link, let url = httpURL(link.url) {
                    Button {
                        NSWorkspace.shared.open(url)
                    } label: {
                        Label(link.label ?? "Open", systemImage: "arrow.up.right.square")
                            .font(.system(size: 12, weight: .semibold))
                    }
                    .buttonStyle(.bordered)
                }
            }
        }
    }

    @ViewBuilder
    func actionLines(_ lines: [AgentActionLine]) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            ForEach(Array(lines.enumerated()), id: \.offset) { _, line in
                HStack(alignment: .firstTextBaseline) {
                    Text(line.label)
                        .font(.system(size: 11))
                        .foregroundColor(appState.themeTextSecondary)
                        .frame(width: 80, alignment: .leading)
                    Text(line.value)
                        .font(line.mono == true ? .system(size: 11, design: .monospaced) : .system(size: 11))
                        .foregroundColor(appState.themeText)
                        .textSelection(.enabled)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
    }

    private func receiptTone(_ status: String) -> (label: String, icon: String, color: Color) {
        switch status {
        case "dry_run": return ("Dry run", "exclamationmark.triangle.fill", .orange)
        case "unknown": return ("Outcome unknown", "exclamationmark.triangle.fill", .orange)
        case "failed": return ("Did not go through", "xmark.octagon.fill", .red)
        case "handoff": return ("Over to you", "arrow.uturn.right.circle.fill", appState.themeAccent)
        default: return ("Done", "checkmark.seal.fill", .green)
        }
    }
}


/// "Before I can buy it": what to add in Settings, with a button that opens
/// the Settings window on the right tab. Card numbers and addresses are never
/// asked for in chat.
private struct PurchaseSetupView: View {
    @Environment(AppState.self) private var appState
    @Environment(\.openSettings) private var openSettings
    let setup: AgentPurchaseSetup

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Before I can buy it")
                .font(.system(size: 12, weight: .semibold))
                .foregroundColor(appState.themeText)
            ForEach(setup.steps, id: \.key) { step in
                HStack(alignment: .top, spacing: 8) {
                    Image(systemName: step.key == "payment_card" ? "creditcard" : "shippingbox")
                        .font(.system(size: 11))
                        .foregroundColor(appState.themeAccent)
                        .frame(width: 14)
                    VStack(alignment: .leading, spacing: 3) {
                        Text("\(step.label) in \(step.where)")
                            .font(.system(size: 12))
                            .foregroundColor(appState.themeText)
                        if let detail = step.detail, !detail.isEmpty {
                            Text(detail)
                                .font(.system(size: 11))
                                .foregroundColor(appState.themeTextSecondary)
                        }
                        Button(step.label) {
                            SettingsTab.select(step.key == "payment_card" ? .paymentCards : .shipping)
                            openSettings()
                        }
                        .buttonStyle(.borderedProminent)
                        .controlSize(.small)
                    }
                }
            }
            Text("Then ask me again. Never paste a card number in chat.")
                .font(.system(size: 11))
                .foregroundColor(appState.themeTextSecondary)
        }
        .padding(10)
        .background(RoundedRectangle(cornerRadius: 12, style: .continuous).fill(appState.themeText.opacity(0.04)))
    }
}
