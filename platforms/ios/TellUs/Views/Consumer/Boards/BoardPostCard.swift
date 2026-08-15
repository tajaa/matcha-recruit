import SwiftUI

struct BoardPostCard: View {
    let post: BoardPost
    let onRedeem: (Listing) -> Void
    var likeDisabled: Bool = false
    var onLikeError: ((String) -> Void)? = nil

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                if post.is_pinned {
                    Image(systemName: "pin.fill").font(.caption).foregroundStyle(.orange)
                }
                Text(post.title).font(.headline)
                Spacer()
                StatusChip(text: post.kind.rawValue)
            }
            if let body = post.body { Text(body).font(.subheadline) }

            if post.kind == .deal, let listing = post.listing {
                Button {
                    onRedeem(listing)
                } label: {
                    HStack {
                        Text(listing.title).font(.subheadline.bold())
                        Spacer()
                        PointsPill(points: listing.points_cost)
                    }
                    .padding(10)
                    .background(TU.ember.opacity(0.12), in: RoundedRectangle(cornerRadius: 8))
                }
            }

            if post.kind == .event, let start = post.event_starts_at {
                Label(Formatters.relativeString(from: start), systemImage: "calendar")
                    .font(.caption).foregroundStyle(TU.textDim)
            }

            HStack(spacing: 12) {
                Text("\(post.approved_reply_count) replies")
                    .font(.caption).foregroundStyle(TU.textDim)
                LikeButton(
                    target: .boardPost, id: post.id,
                    count: post.likeCount, liked: post.likedByMe,
                    disabled: likeDisabled, onError: onLikeError
                )
            }
        }
        .padding()
        .glassCard(radius: 12)
    }
}
