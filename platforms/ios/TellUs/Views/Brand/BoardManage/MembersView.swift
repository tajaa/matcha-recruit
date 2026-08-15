import SwiftUI

struct MembersView: View {
    @Bindable var vm: BoardManageViewModel
    @State private var pendingRemoval: BoardMemberEntry?

    var body: some View {
        if vm.loadState.isLoading(.members) && vm.members.isEmpty {
            ProgressView().frame(maxWidth: .infinity).padding(.vertical, 40)
        } else if vm.members.isEmpty {
            EmptyState(icon: "person.3", title: "No members yet")
        } else {
            List(vm.members) { member in
                HStack {
                    Text(member.account_display_name)
                    Spacer()
                    Text(Formatters.relativeString(from: member.joined_at))
                        .font(.interCaption).foregroundStyle(TU.textDim)
                }
                .swipeActions {
                    Button("Remove", role: .destructive) { pendingRemoval = member }
                }
                .themedRow()
            }
            .listStyle(.insetGrouped)
            .themedScreen()
            .confirmationDialog("Remove this member?", isPresented: Binding(
                get: { pendingRemoval != nil }, set: { if !$0 { pendingRemoval = nil } }
            ), titleVisibility: .visible) {
                Button("Remove", role: .destructive) {
                    if let member = pendingRemoval { Task { await vm.removeMember(member.id) } }
                    pendingRemoval = nil
                }
            }
        }
    }
}
