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
                BoardPostCard(post: post) { listing in
                    vm.redeemFlow.begin()
                    redeemListing = listing
                }
                .listRowSeparator(.hidden)
            }

            Section("Replies") {
                ForEach(replies) { reply in
                    VStack(alignment: .leading, spacing: 4) {
                        HStack {
                            Text(reply.author_name).font(.caption.bold())
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
                                count: reply.likeCount, liked: reply.likedByMe
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
                }
            }
        }
        .safeAreaInset(edge: .bottom) {
            HStack {
                TextField("Add a reply…", text: $newReply)
                    .textFieldStyle(.roundedBorder)
                Button("Send") {
                    Task {
                        await vm.reply(postId: post.id, body: newReply)
                        newReply = ""
                    }
                }
                .disabled(newReply.isEmpty)
            }
            .padding()
            .background(.bar)
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
