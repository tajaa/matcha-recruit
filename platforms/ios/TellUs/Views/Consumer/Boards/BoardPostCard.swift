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
                    Image(systemName: "pin.fill").font(.interCaption).foregroundStyle(.orange)
                }
                Text(post.title).font(.interHeadline)
                Spacer()
                StatusChip(text: post.kind.rawValue)
            }
            if let body = post.body { Text(body).font(.interSubheadline) }

            if post.kind == .deal, let listing = post.listing {
                Button {
                    onRedeem(listing)
                } label: {
                    HStack {
                        Text(listing.title).font(.interSubheadline.bold())
                        Spacer()
                        PointsPill(points: listing.points_cost)
                    }
                    .padding(10)
                    .background(TU.ember.opacity(0.12), in: RoundedRectangle(cornerRadius: 8))
                }
            }

            if post.kind == .promo, let campaign = post.campaign {
                VStack(alignment: .leading, spacing: 8) {
                    if let flyerURL = campaign.flyer_image_url, let url = URL(string: flyerURL) {
                        AsyncImage(url: url) { image in
                            image.resizable().scaledToFit()
                        } placeholder: {
                            ProgressView()
                                .frame(maxWidth: .infinity, minHeight: 120)
                        }
                        .frame(maxHeight: 260)
                        .clipShape(RoundedRectangle(cornerRadius: 8))
                    }

                    HStack {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(campaign.title).font(.interSubheadline.bold())
                            Text(campaign.reward_text)
                                .font(.interCaption)
                                .foregroundStyle(TU.textDim)
                        }
                        Spacer()
                        if let url = URL(string: APIClient.shared.webOrigin + campaign.claim_url) {
                            Link("Claim offer", destination: url)
                                .font(.interCaption.bold())
                                .foregroundStyle(TU.ember)
                        }
                    }
                }
                .padding(10)
                .background(TU.ember.opacity(0.12), in: RoundedRectangle(cornerRadius: 8))
            }

            if post.kind == .event, let start = post.event_starts_at {
                Label(Formatters.relativeString(from: start), systemImage: "calendar")
                    .font(.interCaption).foregroundStyle(TU.textDim)
            }

            HStack(spacing: 12) {
                Text("\(post.approved_reply_count) replies")
                    .font(.interCaption).foregroundStyle(TU.textDim)
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
