import SwiftUI

struct BadgesGrid: View {
    let badges: [BadgeItem]
    private let columns = [GridItem(.adaptive(minimum: 72))]

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Badges").font(.headline)
            LazyVGrid(columns: columns, spacing: 12) {
                ForEach(badges) { badge in
                    VStack(spacing: 4) {
                        Image(systemName: badge.icon ?? "rosette")
                            .font(.title2)
                            .foregroundStyle(badge.earned ? .yellow : .gray.opacity(0.4))
                        Text(badge.name)
                            .font(.caption2)
                            .multilineTextAlignment(.center)
                            .foregroundStyle(badge.earned ? .primary : .secondary)
                    }
                }
            }
        }
    }
}
