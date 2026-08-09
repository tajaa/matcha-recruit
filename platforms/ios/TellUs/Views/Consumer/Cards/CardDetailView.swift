import SwiftUI

/// The card itself, as staff will see it across a counter.
///
/// The QR encodes the card's public URL rather than the bare token so a phone
/// camera that isn't running this app still resolves it to the web card page —
/// the flyer has to work for people who never install anything.
struct CardDetailView: View {
    let card: PromoCard

    @State private var previousBrightness: CGFloat?

    private var qrContent: String {
        APIClient.shared.webOrigin + card.card_url
    }

    var body: some View {
        ScrollView {
            VStack(spacing: 20) {
                VStack(spacing: 6) {
                    Text(card.brand_name)
                        .font(.subheadline)
                        .foregroundStyle(TU.textDim)
                    Text(card.reward_text)
                        .font(.title2.bold())
                        .multilineTextAlignment(.center)
                        .foregroundStyle(.white)
                    Text(card.campaign_title)
                        .font(.footnote)
                        .foregroundStyle(TU.textDim)
                }
                .padding(.top, 12)

                if card.isRedeemable {
                    VStack(spacing: 12) {
                        QRCodeView(content: qrContent)
                            .frame(width: 260, height: 260)
                            .padding(16)
                            .background(Color.white, in: RoundedRectangle(cornerRadius: 18))

                        // Typed fallback for a scanner that won't cooperate —
                        // the same token the camera would have read.
                        Text(card.card_token)
                            .font(.system(.caption, design: .monospaced))
                            .foregroundStyle(TU.textDim)
                            .textSelection(.enabled)

                        Text("Expires \(Formatters.relativeString(from: card.expires_at))")
                            .font(.caption)
                            .foregroundStyle(TU.textDim)
                    }
                } else {
                    spentState
                }
            }
            .padding()
        }
        .background(TU.ink)
        .navigationTitle("Reward card")
        .navigationBarTitleDisplayMode(.inline)
        // A dim screen is the most common reason a counter scanner fails, so
        // the brightness goes up while the code is showing and is put back
        // exactly as it was on the way out.
        .onAppear {
            guard card.isRedeemable else { return }
            previousBrightness = UIScreen.main.brightness
            UIScreen.main.brightness = 1.0
        }
        .onDisappear {
            if let previousBrightness { UIScreen.main.brightness = previousBrightness }
        }
    }

    @ViewBuilder
    private var spentState: some View {
        VStack(spacing: 10) {
            Image(systemName: card.status == "redeemed" ? "checkmark.seal.fill" : "xmark.seal.fill")
                .font(.system(size: 52))
                .foregroundStyle(card.status == "redeemed" ? TU.ember : TU.textDim)
            Text(statusHeadline)
                .font(.headline)
                .foregroundStyle(.white)
            if let at = card.redeemed_at {
                Text(detailLine(at: at))
                    .font(.footnote)
                    .foregroundStyle(TU.textDim)
                    .multilineTextAlignment(.center)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 40)
        .glassCard()
    }

    private var statusHeadline: String {
        switch card.status {
        case "redeemed": return "Already used"
        case "expired": return "Expired"
        case "cancelled": return "No longer valid"
        default: return card.status.capitalized
        }
    }

    private func detailLine(at: String) -> String {
        let when = Formatters.relativeString(from: at)
        if let store = card.redeemed_store_name { return "\(when) at \(store)" }
        return when
    }
}
