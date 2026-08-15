import SwiftUI

struct BoardFeedView: View {
    let slug: String
    let brandName: String
    @State private var vm: BoardFeedViewModel

    init(slug: String, brandName: String) {
        self.slug = slug
        self.brandName = brandName
        _vm = State(initialValue: BoardFeedViewModel(slug: slug))
    }

    var body: some View {
        Group {
            if vm.notAMember {
                VStack(spacing: 12) {
                    switch vm.membershipStatus {
                    case .pending:
                        EmptyState(icon: "clock", title: "Request sent",
                                   hint: "Waiting for \(brandName) to approve your request to join.")
                    case .declined, .removed:
                        EmptyState(icon: "lock", title: "This board isn't open to you right now")
                    default:
                        EmptyState(icon: "lock", title: "You're not a member of this board yet")
                        Button("Request to join") {
                            Task { await vm.requestJoin() }
                        }
                        .buttonStyle(EmberButtonStyle())
                        .padding(.horizontal)
                    }
                    Spacer()
                }
                .themedContainer()
            } else if let page = vm.page {
                List(page.posts) { post in
                    NavigationLink {
                        PostRepliesView(post: post, vm: vm)
                    } label: {
                        BoardPostCard(post: post) { _ in }
                            .allowsHitTesting(false)
                    }
                    .themedRow()
                }
                .listStyle(.insetGrouped)
                .themedScreen()
            } else {
                ProgressView()
            }
        }
        .navigationTitle(brandName)
        .task { await vm.load() }
        .refreshable { await vm.load() }
        .overlay(alignment: .top) { ErrorBanner(message: vm.error).padding(.top, 8) }
    }
}
