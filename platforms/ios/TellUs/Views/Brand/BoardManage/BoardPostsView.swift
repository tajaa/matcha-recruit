import SwiftUI

struct BoardPostsView: View {
    @Bindable var vm: BoardManageViewModel
    @State private var editingPost: BoardPost?
    @State private var pendingDelete: BoardPost?

    var body: some View {
        if vm.posts.isEmpty {
            switch vm.loadState.phase(.posts) {
            case .failed:
                VStack(spacing: 12) {
                    EmptyState(icon: "wifi.exclamationmark", title: "Couldn't load",
                               hint: "Check your connection and try again.")
                    Button("Retry") { Task { await vm.loadTab(.posts, force: true) } }
                        .buttonStyle(EmberButtonStyle())
                        .padding(.horizontal)
                }
            case .loaded:
                EmptyState(icon: "square.and.pencil", title: "No posts yet", hint: "Use the + button above.")
            case .idle, .loading:
                ProgressView().frame(maxWidth: .infinity).padding(.vertical, 40)
            }
        } else {
            List(vm.posts) { post in
                VStack(alignment: .leading, spacing: 4) {
                    HStack {
                        if post.is_pinned { Image(systemName: "pin.fill").font(.interCaption).foregroundStyle(.orange) }
                        Text(post.title).font(.interHeadline)
                        Spacer()
                        StatusChip(text: post.kind.rawValue)
                    }
                    if let body = post.body { Text(body).font(.interSubheadline).lineLimit(2) }
                    Text("\(post.approved_reply_count) replies").font(.interCaption).foregroundStyle(TU.textDim)
                }
                .contentShape(Rectangle())
                .onTapGesture { editingPost = post }
                .swipeActions {
                    Button("Delete", role: .destructive) { pendingDelete = post }
                }
                .themedRow()
            }
            .listStyle(.insetGrouped)
            .themedScreen()
            .sheet(item: $editingPost) { post in
                ComposePostSheet(vm: vm, editing: post)
            }
            .confirmationDialog("Delete this post?", isPresented: Binding(
                get: { pendingDelete != nil }, set: { if !$0 { pendingDelete = nil } }
            ), titleVisibility: .visible) {
                Button("Delete", role: .destructive) {
                    if let post = pendingDelete { Task { await vm.deletePost(post.id) } }
                    pendingDelete = nil
                }
            }
        }
    }
}
