import SwiftUI

struct BoardsListView: View {
    @State private var vm = BoardsListViewModel()

    var body: some View {
        Group {
            if vm.memberships.isEmpty && !vm.isLoading {
                VStack(spacing: 12) {
                    EmptyState(icon: "person.3", title: "No boards yet", hint: "Search for a brand to join their regulars board.")
                    NavigationLink {
                        PlacesView()
                    } label: {
                        Text("Search for a brand")
                    }
                    .buttonStyle(EmberButtonStyle())
                    .padding(.horizontal)
                    Spacer()
                }
                .themedContainer()
            } else {
                List(vm.memberships) { membership in
                    if membership.status == .approved {
                        NavigationLink(membership.brand_name) {
                            BoardFeedView(slug: membership.brand_slug, brandName: membership.brand_name)
                        }
                        .themedRow()
                    } else {
                        HStack {
                            Text(membership.brand_name)
                            Spacer()
                            StatusChip(text: membership.status.rawValue)
                        }
                        .swipeActions {
                            if membership.status == .pending {
                                Button("Cancel request", role: .destructive) {
                                    Task { await vm.cancel(membership.id) }
                                }
                            }
                        }
                        .themedRow()
                    }
                }
                .listStyle(.insetGrouped)
                .themedScreen()
            }
        }
        .navigationTitle("Boards")
        .task { await vm.load() }
        .refreshable { await vm.load() }
        .overlay(alignment: .top) { ErrorBanner(message: vm.error).padding(.top, 8) }
    }
}
