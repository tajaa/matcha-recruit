import SwiftUI

struct HeldRepliesView: View {
    @Bindable var vm: BoardManageViewModel

    var body: some View {
        if vm.heldReplies.isEmpty {
            EmptyState(icon: "checkmark.bubble", title: "No replies awaiting review")
        } else {
            List(vm.heldReplies) { reply in
                VStack(alignment: .leading, spacing: 6) {
                    Text(reply.post_title).font(.caption).foregroundStyle(.secondary)
                    Text(reply.author_name).font(.subheadline.bold())
                    Text(reply.body)
                    HStack {
                        Button("Approve (+15 pts)") { Task { await vm.approveReply(reply.id) } }
                            .buttonStyle(.borderedProminent)
                        Button("Reject") { Task { await vm.rejectReply(reply.id) } }
                            .buttonStyle(.bordered)
                    }
                }
                .padding(.vertical, 4)
            }
            .listStyle(.plain)
        }
    }
}
