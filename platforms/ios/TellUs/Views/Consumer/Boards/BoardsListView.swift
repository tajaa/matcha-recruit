import SwiftUI

struct BoardsListView: View {
    @State private var vm = BoardsListViewModel()

    var body: some View {
        Group {
            if vm.memberships.isEmpty && !vm.isLoading {
                EmptyState(icon: "person.3", title: "No boards yet", hint: "Join a brand's regulars board from their feedback page.")
            } else {
                List(vm.memberships) { membership in
                    if membership.status == .approved {
                        NavigationLink(membership.brand_name) {
                            BoardFeedView(slug: membership.brand_slug, brandName: membership.brand_name)
                        }
                    } else {
                        HStack {
                            Text(membership.brand_name)
                            Spacer()
                            StatusChip(text: membership.status.rawValue)
                        }
                    }
                }
                .listStyle(.plain)
            }
        }
        .navigationTitle("Boards")
        .task { await vm.load() }
        .refreshable { await vm.load() }
        .overlay(alignment: .top) { ErrorBanner(message: vm.error).padding(.top, 8) }
    }
}
