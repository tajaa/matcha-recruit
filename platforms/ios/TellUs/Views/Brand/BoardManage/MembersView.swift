import SwiftUI

struct MembersView: View {
    @Bindable var vm: BoardManageViewModel
    @State private var pendingRemoval: BoardMemberEntry?

    var body: some View {
        if vm.members.isEmpty {
            switch vm.loadState.phase(.members) {
            case .failed:
                VStack(spacing: 12) {
                    EmptyState(icon: "wifi.exclamationmark", title: "Couldn't load",
                               hint: "Check your connection and try again.")
                    Button("Retry") { Task { await vm.loadTab(.members, force: true) } }
                        .buttonStyle(EmberButtonStyle())
                        .padding(.horizontal)
                }
            case .loaded:
                EmptyState(icon: "person.3", title: "No members yet")
            case .idle, .loading:
                ProgressView().frame(maxWidth: .infinity).padding(.vertical, 40)
            }
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
