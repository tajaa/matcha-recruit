import SwiftUI

struct TeamView: View {
    @Bindable var vm: BoardManageViewModel
    @Environment(AppState.self) private var appState
    @State private var newEmail = ""

    private var isOwner: Bool {
        appState.account?.account_type == .brand
    }

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                GlassField {
                    TextField("Add by email", text: $newEmail)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .keyboardType(.emailAddress)
                }
                Button("Add") {
                    let email = newEmail
                    newEmail = ""
                    Task { await vm.addTeamMember(email: email) }
                }
                .buttonStyle(GhostButtonStyle())
                .frame(width: 80)
                .disabled(newEmail.isEmpty)
            }
            .padding()

            if vm.team.isEmpty {
                EmptyState(icon: "person.3", title: "No team members yet")
                Spacer()
            } else {
                List(vm.team) { member in
                    HStack {
                        VStack(alignment: .leading) {
                            Text(member.account_display_name)
                            Text(member.email).font(.interCaption).foregroundStyle(TU.textDim)
                        }
                        Spacer()
                        VStack(alignment: .trailing, spacing: 6) {
                            StatusChip(text: member.role)
                            if isOwner, member.role != "owner" {
                                Toggle("Inbox", isOn: Binding(
                                    get: { member.can_manage_inbox },
                                    set: { enabled in Task { await vm.setInboxAccess(memberID: member.id, enabled: enabled) } }
                                ))
                                .labelsHidden()
                                .toggleStyle(.switch)
                                .tint(TU.ember)
                                .scaleEffect(0.8)
                            }
                        }
                    }
                    .swipeActions {
                        if member.role != "owner" {
                            Button("Remove", role: .destructive) { Task { await vm.removeTeamMember(member.id) } }
                        }
                    }
                    .themedRow()
                }
                .listStyle(.insetGrouped)
                .scrollContentBackground(.hidden)
            }
        }
        .themedContainer()
        .task { await vm.loadTeam() }
    }
}
