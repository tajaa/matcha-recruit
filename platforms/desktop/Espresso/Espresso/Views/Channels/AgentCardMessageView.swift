import SwiftUI
import AppKit

/// Espresso's agent-card messages in a project chat, rendered as cards
/// instead of text walls (server payloads: agent_card/chat_flow.py):
///
/// * result  — top pick with photo, price, rating, reasons and a store link,
///             plus the alternatives it compared;
/// * prompt  — a question ("Want me to buy it?") with quick-reply buttons.
///             A button sends its `reply` as a threaded reply to the question,
///             exactly as if it were typed;
/// * receipt — the purchase outcome (Stripe test charge, handoff, failure).
///
/// Photos are server-rehosted CDN URLs; links open in the browser.
struct AgentCardMessageView: View {
    @Environment(AppState.self) private var appState
    let meta: ChannelMessageMetadata
    /// Message text without the leading ticket marker (used for a question's
    /// heading when the payload has none).
    let text: String
    let onQuickReply: ((String) -> Void)?

    @State private var sentReply: String?

    var body: some View {
        Group {
            if let result = meta.result, meta.kind == "agent_card_result" {
                resultCard(result)
            } else if let view = meta.view, meta.kind == "agent_card_prompt" {
                promptCard(view)
            } else if let receipt = meta.receipt, meta.kind == "agent_card_receipt" {
                receiptCard(receipt)
            }
        }
        .frame(maxWidth: 540, alignment: .leading)
    }

    // MARK: - Result

    @ViewBuilder
    private func resultCard(_ result: AgentChatResult) -> some View {
        card {
            VStack(alignment: .leading, spacing: 10) {
                Text(result.headline)
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundColor(appState.themeText)
                    .fixedSize(horizontal: false, vertical: true)
                if !result.summary.isEmpty {
                    Text(result.summary)
                        .font(.system(size: 12))
                        .foregroundColor(appState.themeTextSecondary)
                        .lineLimit(5)
                        .fixedSize(horizontal: false, vertical: true)
                }
                if let pick = result.topPick {
                    topPick(pick)
                }
                if !result.alternatives.isEmpty {
                    Divider().opacity(0.5)
                    Text("ALSO COMPARED")
                        .font(.system(size: 10, weight: .semibold))
                        .tracking(0.6)
                        .foregroundColor(appState.themeTextSecondary)
                    ForEach(Array(result.alternatives.enumerated()), id: \.offset) { _, alt in
                        alternativeRow(alt)
                    }
                }
                if let sections = result.sections, !sections.isEmpty, result.topPick == nil {
                    Text("Covers: " + sections.joined(separator: " · "))
                        .font(.system(size: 11))
                        .foregroundColor(appState.themeTextSecondary)
                }
                footer(sources: result.sourceCount)
            }
        }
    }

    private func topPick(_ pick: AgentChatPick) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .top, spacing: 12) {
                photo(pick.imageUrl, size: 104)
                VStack(alignment: .leading, spacing: 4) {
                    Text("TOP PICK")
                        .font(.system(size: 10, weight: .bold))
                        .tracking(0.6)
                        .foregroundColor(appState.themeAccent)
                    Text(pick.name)
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundColor(appState.themeText)
                        .lineLimit(3)
                        .fixedSize(horizontal: false, vertical: true)
                    HStack(spacing: 6) {
                        if let brand = pick.brand, !brand.isEmpty {
                            Text(brand).font(.system(size: 11)).foregroundColor(appState.themeTextSecondary)
                        }
                        if let rating = pick.rating {
                            ratingView(rating)
                        }
                    }
                    if let price = pick.priceText {
                        Text(price)
                            .font(.system(size: 16, weight: .bold))
                            .foregroundColor(appState.themeText)
                    }
                }
                Spacer(minLength: 0)
            }
            if let why = pick.why, !why.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(why, id: \.self) { reason in
                        HStack(alignment: .firstTextBaseline, spacing: 6) {
                            Image(systemName: "checkmark.circle.fill")
                                .font(.system(size: 10))
                                .foregroundColor(.green)
                            Text(reason)
                                .font(.system(size: 12))
                                .foregroundColor(appState.themeText)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                }
            }
            if let url = httpURL(pick.buyUrl) {
                Button {
                    NSWorkspace.shared.open(url)
                } label: {
                    Label("View at \(pick.retailer ?? url.host() ?? "store")", systemImage: "arrow.up.right.square")
                        .font(.system(size: 12, weight: .semibold))
                }
                .buttonStyle(.borderedProminent)
                .tint(appState.themeAccent)
                .controlSize(.regular)
            }
        }
        .padding(10)
        .background(RoundedRectangle(cornerRadius: 12, style: .continuous).fill(appState.themeText.opacity(0.04)))
    }

    private func alternativeRow(_ alt: AgentChatPick) -> some View {
        HStack(spacing: 10) {
            photo(alt.imageUrl, size: 40)
            VStack(alignment: .leading, spacing: 1) {
                Text(alt.name)
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(appState.themeText)
                    .lineLimit(1)
                if let brand = alt.brand, !brand.isEmpty {
                    Text(brand).font(.system(size: 10)).foregroundColor(appState.themeTextSecondary).lineLimit(1)
                }
            }
            Spacer(minLength: 8)
            if let price = alt.priceText {
                Text(price).font(.system(size: 12, weight: .semibold)).foregroundColor(appState.themeText)
            }
            if let url = httpURL(alt.buyUrl) {
                Button {
                    NSWorkspace.shared.open(url)
                } label: {
                    Image(systemName: "arrow.up.right.square").font(.system(size: 12))
                }
                .buttonStyle(.plain)
                .foregroundColor(appState.themeTextSecondary)
                .help(alt.retailer ?? url.host() ?? "Open")
            }
        }
    }

    private func ratingView(_ rating: AgentChatRating) -> some View {
        HStack(spacing: 2) {
            Image(systemName: "star.fill").font(.system(size: 9)).foregroundColor(.yellow)
            Text(String(format: "%.1f", rating.value))
                .font(.system(size: 11, weight: .semibold))
                .foregroundColor(appState.themeText)
            if let count = rating.count {
                Text("(\(count.formatted()))").font(.system(size: 11)).foregroundColor(appState.themeTextSecondary)
            }
        }
    }

    private func footer(sources: Int?) -> some View {
        HStack(spacing: 6) {
            if let taskId = meta.taskId {
                Button {
                    appState.pendingOpenTaskId = taskId
                    appState.pendingProjectPanel = .kanban
                } label: {
                    Label("Full page on the card", systemImage: "rectangle.stack")
                        .font(.system(size: 11, weight: .medium))
                }
                .buttonStyle(.plain)
                .foregroundColor(appState.themeAccent)
            }
            if let sources, sources > 0 {
                Text("· \(sources) sources").font(.system(size: 11)).foregroundColor(appState.themeTextSecondary)
            }
        }
    }

    // MARK: - Question

    @ViewBuilder
    private func promptCard(_ view: AgentChatPromptView) -> some View {
        let status = meta.promptStatus ?? "open"
        let answered = sentReply != nil || status != "open"
        card {
            VStack(alignment: .leading, spacing: 10) {
                Text(heading(view))
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundColor(appState.themeText)
                    .fixedSize(horizontal: false, vertical: true)
                if let offer = view.offer {
                    HStack(spacing: 10) {
                        photo(offer.imageUrl, size: 56)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(offer.itemName)
                                .font(.system(size: 12, weight: .semibold))
                                .foregroundColor(appState.themeText)
                                .lineLimit(2)
                            if let retailer = offer.retailer {
                                Text(retailer).font(.system(size: 11)).foregroundColor(appState.themeTextSecondary)
                            }
                        }
                        Spacer(minLength: 8)
                        Text(offer.priceText ?? "Price not confirmed")
                            .font(.system(size: offer.priceText == nil ? 11 : 15, weight: .bold))
                            .foregroundColor(offer.priceText == nil ? .orange : appState.themeText)
                    }
                    .padding(8)
                    .background(RoundedRectangle(cornerRadius: 10, style: .continuous).fill(appState.themeText.opacity(0.04)))
                }
                if answered {
                    Label(statusText(status), systemImage: status == "answered" || sentReply != nil ? "checkmark.circle.fill" : "clock")
                        .font(.system(size: 11, weight: .medium))
                        .foregroundColor(appState.themeTextSecondary)
                } else {
                    buttonRow(view.buttons)
                }
            }
        }
    }

    private func heading(_ view: AgentChatPromptView) -> String {
        if meta.promptKind == "show_result" {
            // "I finished "X". Want to see what I found?" — drop the typed-reply hint.
            let trimmed = text.replacingOccurrences(of: "\\s+Reply\\b[\\s\\S]*$", with: "", options: .regularExpression)
            return trimmed.trimmingCharacters(in: .whitespacesAndNewlines)
        }
        return view.question ?? text
    }

    private func statusText(_ status: String) -> String {
        if let sentReply { return "You replied \u{201C}\(sentReply)\u{201D}" }
        switch status {
        case "answered": return meta.answer.map { "Answered: \($0)" } ?? "Answered"
        case "superseded": return "Replaced by a newer result"
        case "expired": return "This question expired"
        default: return "Closed"
        }
    }

    private func buttonRow(_ buttons: [AgentChatButton]) -> some View {
        // Card choices stack vertically (they carry a detail line); yes/no sit inline.
        let stacked = buttons.contains { $0.detail != nil }
        return Group {
            if stacked {
                VStack(alignment: .leading, spacing: 6) {
                    ForEach(buttons, id: \.self) { quickButton($0) }
                }
            } else {
                HStack(spacing: 8) {
                    ForEach(buttons, id: \.self) { quickButton($0) }
                }
            }
        }
    }

    @ViewBuilder
    private func quickButton(_ button: AgentChatButton) -> some View {
        let label = VStack(alignment: .leading, spacing: 1) {
            Text(button.label).font(.system(size: 12, weight: .semibold))
            if let detail = button.detail {
                Text(detail).font(.system(size: 10)).opacity(0.8)
            }
        }
        let action = {
            sentReply = button.label
            onQuickReply?(button.reply)
        }
        if button.style == "primary" {
            Button(action: action) { label }
                .buttonStyle(.borderedProminent)
                .tint(appState.themeAccent)
                .disabled(onQuickReply == nil)
        } else {
            Button(action: action) { label }
                .buttonStyle(.bordered)
                .disabled(onQuickReply == nil)
        }
    }

    // MARK: - Receipt

    @ViewBuilder
    private func receiptCard(_ r: AgentChatReceipt) -> some View {
        card {
            VStack(alignment: .leading, spacing: 10) {
                HStack(spacing: 6) {
                    Image(systemName: receiptIcon(r.status))
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundColor(receiptColor(r.status))
                    Text(receiptTitle(r.status))
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundColor(appState.themeText)
                    Spacer()
                    Text("TEST MODE")
                        .font(.system(size: 9, weight: .bold))
                        .tracking(0.6)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(Capsule().fill(Color.orange.opacity(0.18)))
                        .foregroundColor(.orange)
                }
                HStack(alignment: .top, spacing: 10) {
                    photo(r.imageUrl, size: 56)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(r.itemName)
                            .font(.system(size: 12, weight: .semibold))
                            .foregroundColor(appState.themeText)
                            .lineLimit(2)
                        Text([r.brand, r.retailer].compactMap { $0 }.joined(separator: " · "))
                            .font(.system(size: 11))
                            .foregroundColor(appState.themeTextSecondary)
                    }
                    Spacer(minLength: 8)
                    if let total = r.totalText {
                        Text(total).font(.system(size: 17, weight: .bold)).foregroundColor(appState.themeText)
                    }
                }
                Divider().opacity(0.5)
                VStack(alignment: .leading, spacing: 4) {
                    if let card = r.cardText { receiptRow("Paid with", card) }
                    if let pi = r.paymentIntentId { receiptRow("Payment", pi, mono: true) }
                    if let ref = r.orderRef { receiptRow("Order ref", ref, mono: true) }
                    if let date = r.date { receiptRow("Date", formatted(date)) }
                    if let error = r.error { receiptRow("Problem", error) }
                }
                Text(receiptNote(r.status))
                    .font(.system(size: 11))
                    .foregroundColor(appState.themeTextSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                HStack(spacing: 12) {
                    if let url = httpURL(r.productUrl) {
                        Button {
                            NSWorkspace.shared.open(url)
                        } label: {
                            Label(r.status == "paid_test" ? "View product" : "Finish checkout", systemImage: "arrow.up.right.square")
                                .font(.system(size: 12, weight: .semibold))
                        }
                        .buttonStyle(.bordered)
                    }
                    footer(sources: nil)
                }
            }
        }
    }

    private func receiptRow(_ label: String, _ value: String, mono: Bool = false) -> some View {
        HStack(alignment: .firstTextBaseline) {
            Text(label).font(.system(size: 11)).foregroundColor(appState.themeTextSecondary).frame(width: 72, alignment: .leading)
            Text(value)
                .font(mono ? .system(size: 11, design: .monospaced) : .system(size: 11))
                .foregroundColor(appState.themeText)
                .textSelection(.enabled)
                .lineLimit(2)
        }
    }

    private func receiptTitle(_ status: String) -> String {
        switch status {
        case "paid_test": return "Purchase complete"
        case "failed": return "Test charge failed"
        case "no_price": return "Approved, no verified price"
        default: return "Approved"
        }
    }

    private func receiptNote(_ status: String) -> String {
        switch status {
        case "paid_test": return "Charged in Stripe test mode. No real money moved."
        case "failed": return "Nothing was charged. The purchase is saved on the card."
        case "no_price": return "Nothing was charged because I couldn't verify the price. Finish checkout at the store."
        default: return "Nothing was charged. Finish checkout at the store."
        }
    }

    private func receiptIcon(_ status: String) -> String {
        switch status {
        case "paid_test": return "checkmark.seal.fill"
        case "failed": return "xmark.octagon.fill"
        default: return "bag.fill"
        }
    }

    private func receiptColor(_ status: String) -> Color {
        switch status {
        case "paid_test": return .green
        case "failed": return .red
        default: return appState.themeAccent
        }
    }

    // MARK: - Shared

    private func card<Content: View>(@ViewBuilder _ content: () -> Content) -> some View {
        content()
            .padding(12)
            .background(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .fill(appState.themeCard)
                    .overlay(
                        RoundedRectangle(cornerRadius: 14, style: .continuous)
                            .stroke(appState.themeBorder, lineWidth: 1)
                    )
            )
    }

    private func photo(_ urlString: String?, size: CGFloat) -> some View {
        Group {
            if let urlString, let url = URL(string: urlString), url.scheme == "https" {
                AsyncImage(url: url) { phase in
                    switch phase {
                    case .success(let image):
                        image.resizable().aspectRatio(contentMode: .fill)
                    default:
                        placeholder(size: size)
                    }
                }
            } else {
                placeholder(size: size)
            }
        }
        .frame(width: size, height: size)
        .background(Color.white)
        .clipShape(RoundedRectangle(cornerRadius: size > 60 ? 12 : 8, style: .continuous))
    }

    private func placeholder(size: CGFloat) -> some View {
        ZStack {
            appState.themeText.opacity(0.06)
            Image(systemName: "photo")
                .font(.system(size: size / 4))
                .foregroundColor(appState.themeTextSecondary)
        }
    }

    private func httpURL(_ string: String?) -> URL? {
        guard let string, let url = URL(string: string),
              ["http", "https"].contains(url.scheme?.lowercased() ?? "") else { return nil }
        return url
    }

    private func formatted(_ iso: String) -> String {
        let parser = ISO8601DateFormatter()
        guard let date = parser.date(from: iso) else { return iso }
        return date.formatted(date: .abbreviated, time: .shortened)
    }
}
