import SwiftUI

struct PostRepliesView: View {
    let post: BoardPost
    @Bindable var vm: BoardFeedViewModel
    @State private var newReply = ""
    @State private var redeemListing: Listing?

    private var replies: [BoardReply] { vm.repliesByPost[post.id] ?? [] }

    var body: some View {
        List {
            Section {
                BoardPostCard(
                    post: post,
                    onRedeem: { listing in
                        vm.redeemFlow.begin()
                        redeemListing = listing
                    },
                    // Mirrors client/tellus BoardPostCard.tsx's disabled prop:
                    // a plain member can't like on a paused/plan-inactive board.
                    likeDisabled: vm.page?.viewer_role == .member
                        && (vm.page?.plan_paused == true || vm.page?.is_active == false),
                    onLikeError: { vm.error = $0 }
                )
                .listRowSeparator(.hidden)
            }

            Section("Replies") {
                ForEach(replies) { reply in
                    VStack(alignment: .leading, spacing: 4) {
                        HStack {
                            Text(reply.author_name).font(.interCaption.bold())
                            if reply.status == .held {
                                StatusChip(text: "awaiting moderation", tint: .orange)
                            }
                            Spacer()
                        }
                        Text(reply.body)
                        // Only approved replies are likeable — the server 404s
                        // a held/rejected one, so don't offer the affordance.
                        if reply.status == .approved {
                            LikeButton(
                                target: .boardReply, id: reply.id,
                                count: reply.likeCount, liked: reply.likedByMe,
                                onError: { vm.error = $0 }
                            )
                        }
                    }
                    .swipeActions {
                        if reply.is_mine && reply.status == .held {
                            Button("Delete", role: .destructive) {
                                Task { await vm.deleteOwnReply(postId: post.id, replyId: reply.id) }
                            }
                        }
                    }
                    .themedRow()
                }
            }
        }
        .listStyle(.insetGrouped)
        .themedScreen()
        .safeAreaInset(edge: .bottom) {
            HStack {
                GlassField {
                    TextField("Add a reply…", text: $newReply)
                }
                Button("Send") {
                    Task {
                        await vm.reply(postId: post.id, body: newReply)
                        newReply = ""
                    }
                }
                .buttonStyle(GhostButtonStyle())
                .frame(width: 90)
                .disabled(newReply.isEmpty)
            }
            .padding()
            .background(TU.ink)
        }
        .navigationTitle(post.title)
        .navigationBarTitleDisplayMode(.inline)
        .task { await vm.loadReplies(postId: post.id) }
        .overlay(alignment: .top) { ErrorBanner(message: vm.error).padding(.top, 8) }
        .sheet(item: $redeemListing) { listing in
            RedeemConfirmSheet(listing: listing, flow: vm.redeemFlow)
        }
    }
}
