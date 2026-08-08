import SwiftUI

struct TeamView: View {
    @Bindable var vm: BoardManageViewModel
    @State private var newEmail = ""

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                TextField("Add by email", text: $newEmail)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .keyboardType(.emailAddress)
                    .textFieldStyle(.roundedBorder)
                Button("Add") {
                    let email = newEmail
                    newEmail = ""
                    Task { await vm.addTeamMember(email: email) }
                }
                .disabled(newEmail.isEmpty)
            }
            .padding()

            if vm.team.isEmpty {
                EmptyState(icon: "person.3", title: "No team members yet")
            } else {
                List(vm.team) { member in
                    HStack {
                        VStack(alignment: .leading) {
                            Text(member.account_display_name)
                            Text(member.email).font(.caption).foregroundStyle(.secondary)
                        }
                        Spacer()
                        StatusChip(text: member.role)
                    }
                    .swipeActions {
                        if member.role != "owner" {
                            Button("Remove", role: .destructive) { Task { await vm.removeTeamMember(member.id) } }
                        }
                    }
                }
                .listStyle(.plain)
            }
        }
        .task { await vm.loadTeam() }
    }
}
