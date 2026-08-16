import SwiftUI

struct DiscoverCard: View {
    let entry: DiscoverEntry
    let onFollow: () -> Void
    let onAddToTellUs: () -> Void
    let onInvite: () -> Void

    var body: some View {
        Group {
            // Hero layout only for a claimed/profiled Tell-Us row with a cover
            // image — deliberately not available to Google rows (rendering a
            // Google photo bills a separate Place Photos fetch per image and
            // can't be hotlinked without exposing the API key). The visual gap
            // is intentional: it's the concrete reason to claim a listing.
            if entry.source == .tellus, let coverURL = entry.cover_url.flatMap(URL.init) {
                heroCard(coverURL: coverURL)
            } else {
                compactCard
            }
        }
        .padding(.vertical, 4)
    }

    @ViewBuilder
    private func heroCard(coverURL: URL) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            AsyncImage(url: coverURL) { image in
                image.resizable().aspectRatio(contentMode: .fill)
            } placeholder: {
                Rectangle().fill(TU.surface)
            }
            .frame(height: 140)
            .frame(maxWidth: .infinity)
            .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))

            HStack(spacing: 6) {
                Text(entry.name).font(.interHeadline).lineLimit(1)
                if !entry.claimed {
                    StatusChip(text: "unclaimed")
                }
            }
            if let tagline = entry.tagline {
                Text(tagline).font(.interFootnote).foregroundStyle(TU.textDim).lineLimit(2)
            }
            metaRow
            actions
        }
    }

    private var compactCard: some View {
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
                metaRow
                actions
            }
        }
    }

    @ViewBuilder
    private var metaRow: some View {
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
        VStack(alignment: .leading, spacing: 4) {
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
                    // Unclaimed — BrandDetailView itself surfaces "Leave
                    // feedback" via the page's own intake_token, not a
                    // Follow/board action.
                    if let slug = entry.slug {
                        NavigationLink("Leave feedback") {
                            BrandDetailView(slug: slug)
                        }
                        .buttonStyle(.bordered).tint(TU.textDim)
                    }
                    Button("Invite", action: onInvite)
                        .buttonStyle(.bordered).tint(TU.ember)
                case .google:
                    Button("Add to Tell-Us", action: onAddToTellUs)
                        .buttonStyle(.bordered).tint(TU.ember)
                    Button("Invite", action: onInvite)
                        .buttonStyle(.bordered).tint(TU.textDim)
                }
            }
            if entry.invite_count > 0 {
                Text("\(entry.invite_count) locals want them here")
                    .font(.interCaption2).foregroundStyle(TU.textDim)
            }
        }
        .font(.interCaption)
        .controlSize(.small)
        .padding(.top, 2)
    }
}

/// Small share sheet presented after a successful invite — same
/// label-plus-copy shape as CampaignQRSheet's ShareLink usage elsewhere in
/// the app, scaled down to a `.presentationDetents` half-sheet since there's
/// no QR code to show here.
struct InviteShareSheet: View {
    let item: DiscoverShareItem
    @State private var copied = false

    var body: some View {
        VStack(spacing: 16) {
            Text(item.text)
                .font(.interSubheadline)
                .multilineTextAlignment(.center)
                .foregroundStyle(TU.textDim)
                .padding(.horizontal)

            ShareLink(item: item.url, message: Text(item.text)) {
                Label("Share", systemImage: "square.and.arrow.up")
            }
            .buttonStyle(.borderedProminent).tint(TU.ember)

            Button {
                UIPasteboard.general.string = item.url.absoluteString
                copied = true
            } label: {
                Label(copied ? "Copied!" : "Copy link", systemImage: "doc.on.doc")
            }
            .buttonStyle(.bordered).tint(TU.textDim)
        }
        .padding(24)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        .themedScreen()
    }
}
