import SwiftUI

struct RedemptionDetailView: View {
    let redemption: Redemption

    var body: some View {
        VStack(spacing: 20) {
            Text(redemption.listing_title ?? "Reward").font(.title2.bold())
            if let code = redemption.code {
                Text(code)
                    .font(.system(.largeTitle, design: .monospaced))
                    .padding()
                    .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 12))
            }
            StatusChip(text: redemption.status.rawValue)
            if let expires = redemption.expires_at {
                Text("Expires \(Formatters.relativeString(from: expires))")
                    .font(.footnote).foregroundStyle(.secondary)
            }
            Text("\(redemption.points_spent) points spent")
                .font(.footnote).foregroundStyle(.secondary)
        }
        .padding()
        .navigationTitle("Redemption")
        .navigationBarTitleDisplayMode(.inline)
    }
}
