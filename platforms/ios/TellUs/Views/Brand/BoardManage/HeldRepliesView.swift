import SwiftUI

struct HeldRepliesView: View {
    @Bindable var vm: BoardManageViewModel

    var body: some View {
        if vm.loadState.isLoading(.held) && vm.heldReplies.isEmpty {
            ProgressView().frame(maxWidth: .infinity).padding(.vertical, 40)
        } else if vm.heldReplies.isEmpty {
            EmptyState(icon: "checkmark.bubble", title: "No replies awaiting review")
        } else {
            List(vm.heldReplies) { reply in
                VStack(alignment: .leading, spacing: 6) {
                    Text(reply.post_title).font(.interCaption).foregroundStyle(.secondary)
                    Text(reply.author_name).font(.interSubheadline.bold())
                    Text(reply.body)
                    HStack {
                        Button("Approve (+15 pts)") { Task { await vm.approveReply(reply.id) } }
                            .buttonStyle(.borderedProminent).tint(TU.ember)
                        Button("Reject") { Task { await vm.rejectReply(reply.id) } }
                            .buttonStyle(.bordered).tint(TU.textDim)
                    }
                }
                .padding(.vertical, 4)
                .themedRow()
            }
            .listStyle(.insetGrouped)
            .themedScreen()
        }
    }
}
