import SwiftUI

struct JoinRequestsView: View {
    @Bindable var vm: BoardManageViewModel

    var body: some View {
        if vm.requests.isEmpty {
            EmptyState(icon: "person.badge.clock", title: "No pending requests")
        } else {
            List(vm.requests) { request in
                VStack(alignment: .leading, spacing: 6) {
                    Text(request.account_display_name).font(.headline)
                    if let note = request.note { Text(note).font(.footnote).foregroundStyle(.secondary) }
                    HStack(spacing: 12) {
                        Label("\(request.review_count)", systemImage: "star.bubble")
                        if request.hearted { Label("hearted", systemImage: "heart.fill").foregroundStyle(.pink) }
                        Label("\(request.redemption_count)", systemImage: "ticket")
                    }
                    .font(.caption).foregroundStyle(.secondary)
                    HStack {
                        Button("Approve") { Task { await vm.approveRequest(request.id) } }
                            .buttonStyle(.borderedProminent)
                        Button("Decline") { Task { await vm.declineRequest(request.id) } }
                            .buttonStyle(.bordered)
                    }
                }
                .padding(.vertical, 4)
            }
            .listStyle(.plain)
        }
    }
}
