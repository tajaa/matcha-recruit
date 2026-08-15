import SwiftUI

struct RedemptionDetailView: View {
    let redemption: Redemption

    var body: some View {
        VStack(spacing: 20) {
            Text(redemption.listing_title ?? "Reward").font(.interTitle2.bold())
            if let code = redemption.code {
                Text(code)
                    .font(.system(.largeTitle, design: .monospaced))
                    .padding()
                    .glassCard(radius: 12)
            }
            StatusChip(text: redemption.status.rawValue)
            if let expires = redemption.expires_at {
                Text("Expires \(Formatters.relativeString(from: expires))")
                    .font(.interFootnote).foregroundStyle(TU.textDim)
            }
            Text("\(redemption.points_spent) points spent")
                .font(.interFootnote).foregroundStyle(TU.textDim)
        }
        .padding()
        .themedContainer()
        .navigationTitle("Redemption")
        .navigationBarTitleDisplayMode(.inline)
    }
}
