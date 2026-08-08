import SwiftUI

struct PostRepliesView: View {
    let post: BoardPost
    @Bindable var vm: BoardFeedViewModel
    @State private var newReply = ""

    private var replies: [BoardReply] { vm.repliesByPost[post.id] ?? [] }

    var body: some View {
        List {
            Section {
                BoardPostCard(post: post) { listing in
                    Task { await vm.redeemBoardListing(listing) }
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
    }
}
