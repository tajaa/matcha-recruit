import SwiftUI

struct JoinRequestsView: View {
    @Bindable var vm: BoardManageViewModel

    var body: some View {
        if vm.requests.isEmpty {
            switch vm.loadState.phase(.requests) {
            case .failed:
                VStack(spacing: 12) {
                    EmptyState(icon: "wifi.exclamationmark", title: "Couldn't load",
                               hint: "Check your connection and try again.")
                    Button("Retry") { Task { await vm.loadTab(.requests, force: true) } }
                        .buttonStyle(EmberButtonStyle())
                        .padding(.horizontal)
                }
            case .loaded:
                EmptyState(icon: "person.badge.clock", title: "No pending requests")
            case .idle, .loading:
                ProgressView().frame(maxWidth: .infinity).padding(.vertical, 40)
            }
        } else {
            List(vm.requests) { request in
                VStack(alignment: .leading, spacing: 6) {
                    Text(request.account_display_name).font(.interHeadline)
                    if let note = request.note { Text(note).font(.interFootnote).foregroundStyle(TU.textDim) }
                    HStack(spacing: 12) {
                        Label("\(request.review_count)", systemImage: "star.bubble")
                        if request.hearted { Label("hearted", systemImage: "heart.fill").foregroundStyle(.pink) }
                        Label("\(request.redemption_count)", systemImage: "ticket")
                    }
                    .font(.interCaption).foregroundStyle(TU.textDim)
                    HStack {
                        Button("Approve") { Task { await vm.approveRequest(request.id) } }
                            .buttonStyle(.borderedProminent).tint(TU.ember)
                        Button("Decline") { Task { await vm.declineRequest(request.id) } }
                            .buttonStyle(.bordered).tint(TU.textDim)
                    }
                }
                .padding(.vertical, 4)
                .themedRow()
            }
            .listStyle(.insetGrouped)
            .themedScreen()
            .refreshable { await vm.refresh(.requests) }
        }
    }
}
