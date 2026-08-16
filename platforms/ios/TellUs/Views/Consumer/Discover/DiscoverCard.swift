import SwiftUI

struct DiscoverCard: View {
    let entry: DiscoverEntry
    let onFollow: () -> Void
    let onAddToTellUs: () -> Void

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            AsyncImage(url: entry.logo_url.flatMap(URL.init)) { image in
                image.resizable().aspectRatio(contentMode: .fill)
            } placeholder: {
                Rectangle().fill(TU.surface)
                    .overlay(Image(systemName: "storefront").foregroundStyle(TU.textDim))
            }
            .frame(width: 52, height: 52)
            .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))

            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 6) {
                    Text(entry.name).font(.interHeadline).lineLimit(1)
                    if entry.source == .google {
                        StatusChip(text: "Google", tint: TU.textDim)
                    } else if !entry.claimed {
                        StatusChip(text: "unclaimed")
                    }
                }

                HStack(spacing: 8) {
                    if let place = placeLine {
                        Text(place).font(.interFootnote).foregroundStyle(TU.textDim)
                    }
                    if let category = entry.category_label {
                        Text(category).font(.interFootnote).foregroundStyle(TU.textDim)
                    }
                }
                .lineLimit(1)

                HStack(spacing: 10) {
                    if let rating = entry.rating, entry.rating_count > 0 {
                        Label(String(format: "%.1f (%d)", rating, entry.rating_count), systemImage: "star.fill")
                    } else if entry.review_count > 0 {
                        Label("\(entry.review_count)", systemImage: "bubble.left.fill")
                    }
                    if let distance = entry.distance_km {
                        Label(String(format: "%.1f km", distance), systemImage: "location.fill")
                    }
                }
                .font(.interCaption).foregroundStyle(TU.textDim)

                actions
            }
        }
        .padding(.vertical, 4)
    }

    private var placeLine: String? {
        switch (entry.city, entry.state) {
        case let (city?, state?): return "\(city), \(state)"
        case let (city?, nil): return city
        default: return entry.address
        }
    }

    @ViewBuilder
    private var actions: some View {
        HStack(spacing: 8) {
            switch entry.source {
            case .tellus where entry.claimed:
                Button(entry.followed ? "Following" : "Follow", action: onFollow)
                    .buttonStyle(.bordered).tint(entry.followed ? TU.textDim : TU.ember)
                if let slug = entry.slug {
                    NavigationLink(entry.has_board ? "View board" : "See reviews") {
                        BrandDetailView(slug: slug)
                    }
                    .buttonStyle(.bordered).tint(TU.textDim)
                }
            case .tellus:
                // Unclaimed — BrandDetailView itself surfaces "Leave feedback"
                // via the page's own intake_token, not a Follow/board action.
                if let slug = entry.slug {
                    NavigationLink("Leave feedback") {
                        BrandDetailView(slug: slug)
                    }
                    .buttonStyle(.bordered).tint(TU.textDim)
                }
            case .google:
                Button("Add to Tell-Us", action: onAddToTellUs)
                    .buttonStyle(.bordered).tint(TU.ember)
            }
        }
        .font(.interCaption)
        .controlSize(.small)
        .padding(.top, 2)
    }
}
