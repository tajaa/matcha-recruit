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
                    EmptyState(icon: "lock", title: "You're not a member of this board yet")
                    Button("Request to join") {
                        Task { try? await BoardService.shared.join(slug: slug, note: nil); await vm.load() }
                    }
                }
            } else if let page = vm.page {
                List(page.posts) { post in
                    NavigationLink {
                        PostRepliesView(post: post, vm: vm)
                    } label: {
                        BoardPostCard(post: post) { _ in }
                            .allowsHitTesting(false)
                    }
                }
                .listStyle(.plain)
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
